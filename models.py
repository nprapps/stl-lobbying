#!/usr/bin/env python

import datetime
import re

import csvkit
from peewee import *
from playhouse.sqlite_ext import SqliteExtDatabase

import app_config

database = SqliteExtDatabase('stl-lobbying.db')

class SlugModel(Model):
    """
    A legislator.
    """
    slug_fields = []

    slug = CharField()

    def save(self, *args, **kwargs):
        """
        Slugify before saving!
        """
        if not self.slug:
            self.slugify()

        super(SlugModel, self).save(*args, **kwargs)

    def slugify(self):
        """
        Generate a slug.
        """
        bits = []

        for field in self.slug_fields:
            attr = getattr(self, field)

            if attr:
                attr = attr.lower()
                attr = re.sub(r'[^\w\s]', '', attr)
                attr = re.sub(r'\s+', '-', attr)

                bits.append(attr)

        base_slug = '-'.join(bits)

        slug = base_slug
        i = 1

        while Legislator.select().where(Legislator.slug == slug).count():
            i += 1
            slug = '%s-%i' % (base_slug, i)

        self.slug = slug

class Lobbyist(SlugModel):
    """
    A lobbyist.
    """
    slug_fields = ['first_name', 'last_name']

    first_name = CharField()
    last_name = CharField()
    
    class Meta:
        database = database

class Legislator(SlugModel):
    """
    A legislator.
    """
    OFFICE_SHORT_NAMES = {
        'Senator': 'Sen.',
        'Representative': 'Rep.'
    }

    slug_fields = ['office', 'first_name', 'last_name']

    first_name = CharField()
    last_name = CharField()
    office = CharField()
    district = CharField()
    party = CharField()
    ethics_name = CharField(null=True)
    phone = CharField()
    year_elected = IntegerField(null=True)
    hometown = CharField()
    
    class Meta:
        database = database

    def url(self):
        return '%s/legislators/%s/' % (app_config.S3_BASE_URL, self.slug)

    def display_name(self):
        office = self.OFFICE_SHORT_NAMES[self.office] 

        return '%s %s %s' % (office, self.first_name, self.last_name)

class Group(SlugModel):
    slug_fields = ['name']

    name = CharField()
    
    class Meta:
        database = database

class Organization(SlugModel):
    slug_fields = ['name']

    name = CharField()
    category = CharField()
    
    class Meta:
        database = database

    def url(self):
        return '%s/organization/%s/' % (app_config.S3_BASE_URL, self.slug)

class Expenditure(Model):
    """
    An expenditure.
    """
    lobbyist = ForeignKeyField(Lobbyist, related_name='expenditures')
    report_period = DateField()
    recipient = CharField()
    recipient_type = CharField()
    legislator = ForeignKeyField(Legislator, related_name='expenditures', null=True)
    event_date = DateField()
    category = CharField()
    description =  CharField()
    cost = FloatField()
    organization = ForeignKeyField(Organization, related_name='expenditures')
    group = ForeignKeyField(Group, related_name='expenditures', null=True)
    ethics_id = IntegerField()
    is_solicitation = BooleanField()
    
    class Meta:
        database = database

def delete_tables():
    """
    Clear data from sqlite.
    """
    for cls in [Group, Lobbyist, Legislator, Organization, Expenditure]:
        try:
            cls.drop_table()
        except:
            continue

def create_tables():
    """
    Create database tables for each model.
    """
    for cls in [Group, Lobbyist, Legislator, Organization, Expenditure]:
        cls.create_table()

class LobbyLoader:
    """
    Load expenditures from files.
    """
    # Folks we have data for, but predate our period of interest
    SKIP_LEGISLATORS = ['PURGASON, CHUCK']
    SKIP_TYPES = ['Local Government Official', 'Public Official', 'ATTORNEY GENERAL', 'STATE TREASURER', 'GOVERNOR', 'STATE AUDITOR', 'LIEUTENANT GOVERNOR', 'SECRETARY OF STATE', 'JUDGE']
    ERROR_DATE_MIN = datetime.date(2012, 1, 1)
    ERROR_DATE_MAX = datetime.datetime.today().date()

    organization_name_lookup = {}
    expenditures = []

    warnings = []
    errors = []

    individual_rows = 0
    group_rows = 0
    amended_rows = 0
    lobbyists_created = 0
    legislators_created = 0
    organizations_created = 0
    groups_created = 0

    def __init__(self):
        self.legislators_demographics_filename = 'data/legislator_demographics.csv'
        self.organization_name_lookup_filename = 'data/organization_name_lookup.csv'
        self.individual_data_filename = 'data/individual_expenditures.csv'
        self.solicitation_data_filename = 'data/solicitation_expenditures.csv'
        self.group_data_filename = 'data/group_expenditures.csv'

    def info(self, msg):
        pass

    def warn(self, msg):
        self.warnings.append(msg)

    def error(self, msg):
        self.errors.append(msg)

    def load_organization_name_lookup(self):
        """
        Load organiation name standardization mapping.
        """
        with open(self.organization_name_lookup_filename) as f:
            reader = csvkit.CSVKitReader(f)
            reader.next()

            for row in reader:
                row = map(unicode.strip, row)

                ethics_name = row[0]
                correct_name = row[1]
                category = row[2]

                if not correct_name:
                    correct_name = ethics_name

                self.organization_name_lookup[ethics_name] = correct_name

                try:
                    Organization.get(Organization.name == correct_name)
                except Organization.DoesNotExist:
                    Organization.create(
                        name=correct_name,
                        category=category
                    )

    def load_lobbyist(self, first_name, last_name):
        """
        Get or create a lobbyist.
        """
        try:
            return False, Lobbyist.get(Lobbyist.first_name==first_name, Lobbyist.last_name==last_name)
        except Lobbyist.DoesNotExist:
            pass

        lobbyist = Lobbyist(
            first_name=first_name,
            last_name=last_name
        )

        lobbyist.save()

        return True, lobbyist 

    def load_organization(self, name):
        """
        Get or create an organization.
        """
        if name in self.organization_name_lookup:
            lookup = self.organization_name_lookup[name]

            if lookup:
                name = lookup
        
            return Organization.get(Organization.name==name)
        else:
            self.error('Organization name "%s" not in lookup table' % name)

            return None

    def load_group(self, name):
        """
        Get or create a group.
        """
        try:
            return False, Group.get(Group.name==name)
        except Group.DoesNotExist:
            pass

        group = Group(
            name=name
        )

        group.save()

        return True, group

    def load_legislators(self):
        """
        Load legislator demographics.
        """
        VALID_OFFICES = ['Representative', 'Senator']
        VALID_PARTIES = ['Republican', 'Democratic']

        with open(self.legislators_demographics_filename) as f:
            reader = csvkit.CSVKitDictReader(f)
            rows = list(reader)

        i = 0

        for row in rows:
            i += 1

            for k in row:
                row[k] = row[k].strip()
            
            office = row['office']

            if office not in VALID_OFFICES:
                self.warn('%05i -- Not a valid office: "%s"' % (i, office))

            party = row['party']

            if not party:
                self.error('%05i -- No party affiliation for "%s": "%s"' % (i, office, row['ethics_name']))
            elif party not in VALID_PARTIES:
                self.warn('%05i -- Unknown party name: "%s"' % (i, party))

            year_elected = row['year_elected']

            if year_elected:
                year_elected = int(year_elected)
            else:
                year_elected = None
                self.error('%05i -- No year elected for "%s": "%s"' % (i, office, row['ethics_name']))

            legislator = Legislator(
                first_name=row['first_name'],
                last_name=row['last_name'],
                office=office,
                district=row['district'],
                party=party,
                ethics_name=row['ethics_name'],
                phone=row['phone'],
                year_elected=year_elected,
                hometown=row['hometown']
            )

            legislator.save()

            self.legislators_created += 1

    def load_individual_expenditures(self, filename, solicitations=False):
        """
        Load individual expenditures from files.
        """
        # Load data
        with open(filename) as f:
            reader = csvkit.CSVKitDictReader(f)
            rows = list(reader)

        i = 0

        for row in rows:
            i += 1

            # Strip whitespace
            for k, v in row.items():
                row[k] = v.strip()

            # Amended?
            if row['If Amended'] == 'Amended':
                self.amended_rows += 1
                continue

            # Lobbyist
            created, lobbyist = self.load_lobbyist(row['Lob F Name'], row['Lob L Name'])

            if created:
                self.lobbyists_created += 1 

            # Report period
            report_period = datetime.datetime.strptime(row['Report'], '%b-%y').date()

            if report_period < self.ERROR_DATE_MIN:
                self.error('%05i -- Report date too old: %s' % (i, row['Report']))
            elif report_period > self.ERROR_DATE_MAX:
                self.error('%05i -- Report date too new: %s' % (i, row['Report']))

            # Recipient
            recipient, recipient_type = map(unicode.strip, row['Recipient'].rsplit(' - ', 1))

            if recipient in self.SKIP_LEGISLATORS:
                self.info('%05i -- Skipping "%s": "%s" for "%s": "%s"' % (i, recipient_type, recipient, legislator_type, legislator_name))
                continue

            # NB: Brute force correction for name mispelling in one state dropdown
            if recipient == 'CARPENTER, JOHN':
                recipient = 'CARPENTER, JON'

            # Legislator
            legislator = None

            if recipient_type in ['Senator', 'Representative']:
                try:
                    legislator = Legislator.get(Legislator.ethics_name==recipient, Legislator.office==recipient_type)
                except Legislator.DoesNotExist:
                    self.error('%05i -- No matching legislator for "%s": "%s"' % (i, recipient_type, recipient))
                    continue
            elif recipient_type in ['Employee or Staff', 'Spouse or Child']:
                legislator_name, legislator_type = map(unicode.strip, row['Pub Off'].rsplit(' - ', 1))

                if legislator_name in self.SKIP_LEGISLATORS:
                    self.info('%05i -- Skipping "%s": "%s" for "%s": "%s"' % (i, recipient_type, recipient, legislator_type, legislator_name))
                    continue

                # NB: Brute force correction for name mispelling in one state dropdown
                if legislator_name == 'CARPENTER, JOHN':
                    legislator_name = 'CARPENTER, JON'

                if legislator_type in self.SKIP_TYPES:
                    self.info('%05i -- Skipping "%s": "%s" for "%s": "%s"' % (i, recipient_type, recipient, legislator_type, legislator_name))
                    continue

                try:
                    legislator = Legislator.get(Legislator.ethics_name==legislator_name, Legislator.office==legislator_type)
                except Legislator.DoesNotExist:
                    self.error('%05i -- No matching legislator for "%s": "%s"' % (i, legislator_type, legislator_name))
                    continue
            elif recipient_type in self.SKIP_TYPES:
                self.info('%05i -- Skipping "%s": "%s"' % (i, recipient_type, recipient))
                continue
            else:
                self.error('%05i -- Unknown recipient type, "%s": "%s"' % (i, recipient_type, recipient))
                continue

            # Event date
            bits = map(int, row['Date'].split('/'))
            event_date = datetime.date(bits[2], bits[0], bits[1])

            if event_date < self.ERROR_DATE_MIN:
                self.error('%05i -- Event date too old: %s' % (i, row['Date']))
            elif event_date > self.ERROR_DATE_MAX:
                self.error('%05i -- Event date too new: %s' % (i, row['Date']))

            # Cost
            cost = row['Cost'].strip('$').replace(',', '')

            if '(' in cost or '-' in cost:
                self.error('%05i -- Negative cost outside an amendment!' % i)
                continue

            cost = float(cost)

            # Organization
            organization = self.load_organization(row['Principal'])

            if not organization:
                continue

            # Create it!
            self.expenditures.append(Expenditure(
                lobbyist=lobbyist,
                report_period=report_period,
                recipient=recipient,
                recipient_type=recipient_type,
                legislator=legislator,
                event_date=event_date,
                category=row['Type'],
                description=row['Description'],
                cost=cost,
                organization=organization,
                group=None,
                ethics_id=int(row['Sol ID'] if solicitations else row['Indv ID']),
                is_solicitation=solicitations
            ))

        self.individual_rows = i 

    def load_group_expenditures(self):
        """
        Load group expenditures from files.
        """
        # Load data
        with open(self.group_data_filename) as f:
            reader = csvkit.CSVKitDictReader(f)
            rows = list(reader)

        i = 0

        for row in rows:
            i += 1

            # Strip whitespace
            for k, v in row.items():
                row[k] = v.strip()

            # Amended?
            if row['If Amended'] == 'Amended':
                self.amended_rows += 1
                continue

            # Lobbyist
            created, lobbyist = self.load_lobbyist(row['Lob F Name'], row['Lob L Name'])

            if created:
                self.lobbyists_created += 1 

            # Report period
            report_period = datetime.datetime.strptime(row['Report'], '%b-%y').date()

            if report_period < self.ERROR_DATE_MIN:
                self.error('%05i -- Report date too old: %s' % (i, row['Report']))
            elif report_period > self.ERROR_DATE_MAX:
                self.error('%05i -- Report date too new: %s' % (i, row['Report']))

            # Group
            created, group = self.load_group(row['Group'])

            if created:
                self.groups_created += 1

            # Event date
            bits = map(int, row['Date'].split('/'))
            event_date = datetime.date(bits[2], bits[0], bits[1])

            if event_date < self.ERROR_DATE_MIN:
                self.error('%05i -- Event date too old: %s' % (i, row['Date']))
            elif event_date > self.ERROR_DATE_MAX:
                self.error('%05i -- Event date too new: %s' % (i, row['Date']))

            # Cost
            cost = row['Cost'].strip('$').replace(',', '')

            if '(' in cost or '-' in cost:
                self.error('%05i -- Negative cost outside an amendment!' % i)
                continue

            cost = float(cost)

            # Organization
            organization = self.load_organization(row['Principal'])

            if not organization:
                continue

            # Create it!
            self.expenditures.append(Expenditure(
                lobbyist=lobbyist,
                report_period=report_period,
                recipient='',
                recipient_type='',
                legislator=None,
                event_date=event_date,
                category=row['Type'],
                description=row['Description'],
                cost=cost,
                organization=organization,
                group=group,
                ethics_id=int(row['Grp ID']),
                is_solicitation=False
            ))

        self.group_rows = i

    def run(self):
        """
        Run the loader and output summary.
        """
        self.load_organization_name_lookup()
        self.load_legislators()
        self.load_individual_expenditures(self.individual_data_filename, False)
        self.load_individual_expenditures(self.solicitation_data_filename, True)
        self.load_group_expenditures()

        if self.warnings:
            print 'WARNINGS'
            print '--------'

            for warning in self.warnings:
                print warning

            print ''

        if self.errors:
            print 'ERRORS'
            print '------'

            for error in self.errors:
                print error

            print ''

            # return


        for expenditure in self.expenditures:
            expenditure.save()

        print 'SUMMARY'
        print '-------'

        print 'Processed %i individual rows' % self.individual_rows
        print 'Processed %i group rows' % self.group_rows 
        print ''
        print 'Encountered %i warnings' % len(self.warnings)
        print 'Encountered %i errors' % len(self.errors)
        print 'Skipped %i amended rows' % self.amended_rows 
        print ''
        print 'Imported %i expenditures' % len(self.expenditures)
        print 'Created %i lobbyists' % self.lobbyists_created
        print 'Created %i legislators' % self.legislators_created
