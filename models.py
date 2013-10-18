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
    slug_fields = ['name']

    name = CharField()
    
    class Meta:
        database = database

class Legislator(SlugModel):
    """
    A legislator.
    """
    slug_fields = ['name']

    name = CharField()
    office = CharField()
    district = CharField()
    party = CharField()
    ethics_name = CharField(null=True)
    
    class Meta:
        database = database

    def url(self):
        return '%s/legislator/%s/' % (app_config.S3_BASE_URL, self.slug)

class Group(SlugModel):
    slug_fields = ['name']

    name = CharField()
    
    class Meta:
        database = database

class Organization(SlugModel):
    slug_fields = ['name']

    name = CharField()
    
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
    SKIP_TYPES = ['Local Government Official', 'Public Official', 'ATTORNEY GENERAL', 'STATE TREASURER', 'GOVERNOR', 'STATE AUDITOR', 'LIEUTENANT GOVERNOR', 'SECRETARY OF STATE', 'JUDGE']
    ERROR_DATE_MIN = datetime.date(2010, 1, 1)
    ERROR_DATE_MAX = datetime.date(2020, 1, 1)

    organization_name_lookup = {}
    expenditures = []

    warnings = []
    errors = []

    individual_rows = 0
    group_rows = 0
    lobbyists_created = 0
    legislators_created = 0
    organizations_created = 0
    groups_created = 0

    def __init__(self):
        self.legislators_demographics_filename = 'data/legislator_demographics.csv'
        self.organization_name_lookup_filename = 'data/organization_name_lookup.csv'
        self.individual_data_filename = 'data/sample_data.csv'
        self.group_data_filename = 'data/sample_group_data.csv'

    def warn(self, msg):
        self.warnings.append(msg)

    def error(self, msg):
        self.errors.append(msg)

    def strip_nicknames(self, name):
        if '(' in name:
            return name.split('(')[0].strip()

        return name

    def load_organization_name_lookup(self):
        """
        Load organiation name standardization mapping.
        """
        with open(self.organization_name_lookup_filename) as f:
            reader = csvkit.CSVKitReader(f)
            reader.next()

            for row in reader:
                self.organization_name_lookup[row[0].strip()] = row[1].strip()

    def load_lobbyist(self, name):
        """
        Get or create a lobbyist.
        """
        try:
            return False, Lobbyist.get(Lobbyist.name==name)
        except Lobbyist.DoesNotExist:
            pass

        lobbyist = Lobbyist(
            name=name
        )

        lobbyist.save()

        return True, lobbyist 

    def load_organization(self, name):
        """
        Get or create an organization.
        """
        if name not in self.organization_name_lookup:
            self.warn('Organization name "%s" not in lookup table' % name)

        lookup = self.organization_name_lookup[name]

        if lookup:
            name = lookup

        try:
            return False, Organization.get(Organization.name==name)
        except Organization.DoesNotExist:
            pass

        organization = Organization(
            name=name
        )

        organization.save()

        return True, organization

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

            legislator = Legislator(
                name='%(first_name)s %(last_name)s' % row,
                office=office,
                district=row['district'],
                party=party,
                ethics_name=row['ethics_name']
            )

            legislator.save()

            self.legislators_created += 1

    def load_individual_expenditures(self):
        """
        Load individual expenditures from files.
        """
        # Load data
        with open(self.individual_data_filename) as f:
            reader = csvkit.CSVKitDictReader(f)
            rows = list(reader)

        i = 0

        for row in rows:
            i += 1

            # Strip whitespace
            for k, v in row.items():
                row[k] = v.strip()

            # Lobbyist
            created, lobbyist = self.load_lobbyist('%s %s' % (row['Lob F Name'], row['Lob L Name']))

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
            recipient = self.strip_nicknames(recipient)

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
                legislator_name = self.strip_nicknames(legislator_name)

                if legislator_type in self.SKIP_TYPES:
                    #self.warn('%05i -- Skipping "%s": "%s" for "%s": "%s"' % (i, recipient_type, recipient, legislator_type, legislator_name))
                    continue

                try:
                    legislator = Legislator.get(Legislator.ethics_name==legislator_name, Legislator.office==legislator_type)
                except Legislator.DoesNotExist:
                    self.error('%05i -- No matching legislator for "%s": "%s"' % (i, legislator_type, legislator_name))
                    continue
            elif recipient_type in self.SKIP_TYPES:
                #self.warn('%05i -- Skipping "%s": "%s"' % (i, recipient_type, recipient))
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
                self.error('%05i -- Negative cost!' % i)
                continue

            cost = float(cost)

            # Organization
            created, organization = self.load_organization(row['Principal'])

            if created:
                self.organizations_created += 1

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
                group=None
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

            # Lobbyist
            created, lobbyist = self.load_lobbyist('%s %s' % (row['Lob F Name'], row['Lob L Name']))

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
                self.error('%05i -- Negative cost!' % i)
                continue

            cost = float(cost)

            # Organization
            created, organization = self.load_organization(row['Principal'])

            if created:
                self.organizations_created += 1

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
                group=group
            ))

        self.group_rows = i

    def run(self):
        """
        Run the loader and output summary.
        """
        self.load_organization_name_lookup()
        self.load_legislators()
        self.load_individual_expenditures()
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
        print 'Imported %i expenditures' % len(self.expenditures)
        print 'Created %i lobbyists' % self.lobbyists_created
        print 'Created %i legislators' % self.legislators_created
        print 'Created %i organizations' % self.organizations_created
