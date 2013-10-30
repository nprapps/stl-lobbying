#!/usr/bin/env python

import datetime
import re

import csvkit
from peewee import *
from playhouse.sqlite_ext import SqliteExtDatabase
import xlrd

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

    NB: Only current legislators get models.
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
    vacant = BooleanField()
    
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
        return '%s/organizations/%s/' % (app_config.S3_BASE_URL, self.slug)

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
    SKIP_TYPES = ['Local Government Official', 'Public Official', 'ATTORNEY GENERAL', 'STATE TREASURER', 'GOVERNOR', 'STATE AUDITOR', 'LIEUTENANT GOVERNOR', 'SECRETARY OF STATE', 'JUDGE', 'GOVERNOR ELECT', 'CHIEF JUSTICE']
    ERROR_DATE_MIN = datetime.date(2003, 1, 1)
    ERROR_DATE_MAX = datetime.datetime.today().date()

    organization_name_lookup = {}
    expenditures = []
    datemode = None

    warnings = []
    errors = []

    individual_rows = 0
    group_rows = 0
    amended_rows = 0
    lobbyists_created = 0
    legislators_created = 0
    organizations_created = 0
    groups_created = 0

    def __init__(self, first_year=2004):
        self.first_year = first_year

        self.expenditures_xlsx = 'data/expenditures/%i.xlsx'
        self.legislators_demographics_filename = 'data/legislator_demographics.csv'
        self.organization_name_lookup_filename = 'data/organization_name_lookup.csv'

    def _format_log(self, msg, year=None, line=None):
        if line:
            msg = '%05i -- %s' % (line, msg)

        if year:
            msg = '%i -- %s' % (year, msg)
        
        return msg

    def info(self, msg, year=None, line=None):
        pass

    def warn(self, msg, year=None, line=None):
        self.warnings.append(self._format_log(msg, year, line))

    def error(self, msg, year=None, line=None):
        self.errors.append(self._format_log(msg, year, line))

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
                category = row[2] or 'Other'

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

            # Process vacant seats
            if row['last_name'].upper() == 'VACANT':
                Legislator.create(
                    first_name='',
                    last_name='',
                    office=office,
                    district=row['district'],
                    party='',
                    ethics_name='',
                    phone='',
                    year_elected=0,
                    hometown='',
                    vacant=True
                )

                self.legislators_created += 1

                continue
            
            office = row['office']

            if office not in VALID_OFFICES:
                self.warn('Not a valid office: "%s"' % (office), year, i)

            party = row['party']

            if not party:
                self.error( 'No party affiliation for "%s": "%s"' % (office, row['ethics_name']), year, i)
            elif party not in VALID_PARTIES:
                self.warn('Unknown party name: "%s"' % (party), year, i)

            year_elected = row['year_elected']

            if year_elected:
                year_elected = int(year_elected)
            else:
                self.error('No year elected for "%s": "%s"' % (office, row['ethics_name']), year, i)
                year_elected = None

            legislator = Legislator(
                first_name=row['first_name'],
                last_name=row['last_name'],
                office=office,
                district=row['district'],
                party=party,
                ethics_name=row['ethics_name'],
                phone=row['phone'],
                year_elected=year_elected,
                hometown=row['hometown'],
                vacant=False
            )

            legislator.save()

            self.legislators_created += 1

    def load_individual_expenditures(self, year, rows, solicitations=False):
        """
        Load individual expenditures from files.
        """
        i = 0

        for row in rows:
            i += 1

            # Strip whitespace
            for k, v in row.items():
                if type(row[k]) is unicode:
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
            if not row['Report']:
                self.warn('Skipping row with no report date!', year, i)
                continue

            report_period = datetime.datetime(*xlrd.xldate_as_tuple(row['Report'], self.datemode)).date()

            if report_period < self.ERROR_DATE_MIN:
                self.warn('Skipping: report date too old, %s' % (report_period), year, i)
                continue
            elif report_period > self.ERROR_DATE_MAX:
                self.warn('Skipping: report date too new, %s' % (report_period), year, i)
                continue

            # Recipient
            try:
                recipient, recipient_type = map(unicode.strip, row['Recipient'].rsplit(' - ', 1))
            except ValueError:
                self.warn('Skipping "%s", no recipient type' % (recipient), year, i)
                continue

            # NB: Brute force correction for name mispelling in one state dropdown
            if recipient == 'CARPENTER, JOHN':
                recipient = 'CARPENTER, JON'

            # Legislator
            legislator = None

            if recipient_type in ['Senator', 'Representative']:
                try:
                    legislator = Legislator.get(Legislator.ethics_name==recipient)
                except Legislator.DoesNotExist:
                    self.info('Not a current legislator: %s %s' % (recipient_type, recipient), year, i)
            elif recipient_type in ['Employee or Staff', 'Spouse or Child']:
                try:
                    legislator_name, legislator_type = map(unicode.strip, row['Pub Off'].rsplit(' - ', 1))
                except ValueError:
                    self.warn('Skipping "%s", no recipient type' % (legislator_name), year, i)
                    continue

                # NB: Brute force correction for name mispelling in one state dropdown
                if legislator_name == 'CARPENTER, JOHN':
                    legislator_name = 'CARPENTER, JON'

                if legislator_type in self.SKIP_TYPES:
                    self.info('Skipping "%s": "%s" for "%s": "%s"' % (recipient_type, recipient, legislator_type, legislator_name), line=i)
                    continue

                try:
                    legislator = Legislator.get(Legislator.ethics_name==legislator_name)
                except Legislator.DoesNotExist:
                    self.info('Not a current legislator: %s %s' % (legislator_type, legislator_name), year, i)
            elif recipient_type in self.SKIP_TYPES:
                self.info('Skipping "%s": "%s"' % (recipient_type, recipient), line=i)
                continue
            else:
                self.error('Unknown recipient type, "%s": "%s"' % (recipient_type, recipient), year, i)
                continue

            # Event date
            event_date = datetime.datetime(*xlrd.xldate_as_tuple(row['Date'], self.datemode)).date()

            if event_date < self.ERROR_DATE_MIN:
                self.warn('Skipping, event date too old: %s' % (event_date), year, i)
            elif event_date > self.ERROR_DATE_MAX:
                self.warn('Skipping, event date too new: %s' % (event_date), year, i)

            # Cost
            cost = row['Cost']

            if cost < 0:
                self.error('Negative cost outside an amendment!' % i, year, i)
                continue

            # Organization
            organization = self.load_organization(row['Principal'])

            if not organization:
                self.error('Organization name "%s" not in lookup table' % row['Principal'], year, i)
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

        self.individual_rows += i 

    def load_group_expenditures(self, year, rows):
        """
        Load group expenditures from files.
        """
        i = 0

        for row in rows:
            i += 1

            # Strip whitespace
            for k, v in row.items():
                if type(row[k]) is unicode:
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
            report_period = datetime.datetime(*xlrd.xldate_as_tuple(row['Report'], self.datemode)).date()

            if report_period < self.ERROR_DATE_MIN:
                self.warn('Skipping, report date too old: %s' % (report_period), year, i)
            elif report_period > self.ERROR_DATE_MAX:
                self.warn('Skipping, report date too new: %s' % (report_period), year, i)

            # Group
            created, group = self.load_group(row['Group'])

            if created:
                self.groups_created += 1

            # Event date
            event_date = datetime.datetime(*xlrd.xldate_as_tuple(row['Date'], self.datemode)).date()

            if event_date < self.ERROR_DATE_MIN:
                self.warn('Skipping, event date too old: %s' % (event_date), year, i)
            elif event_date > self.ERROR_DATE_MAX:
                self.warn('Skipping, event date too new: %s' % (event_date), year, i)

            # Cost
            cost = row['Cost']

            if cost < 0:
                self.error('Negative cost outside an amendment!' % i, year, i)
                continue

            # Organization
            organization = self.load_organization(row['Principal'])

            if not organization:
                self.error('Organization name "%s" not in lookup table' % row['Principal'], year, i)
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

        self.group_rows += i

    def run(self):
        """
        Run the loader and output summary.
        """
        print 'Loading organization names'
        self.load_organization_name_lookup()

        print 'Loading legislator demographics'
        self.load_legislators()

        print ''

        for year in range(self.first_year, datetime.datetime.today().year + 1):
            print year
            print '----'
            print ''

            path = self.expenditures_xlsx % year

            print 'Opening %s' % path

            book = xlrd.open_workbook(path)
            self.datemode = book.datemode

            tables = []

            for sheet in book.sheets():
                columns = sheet.row_values(0)
                rows = []

                for n in range(1, sheet.nrows):
                    rows.append(dict(zip(columns, sheet.row_values(n))))

                tables.append(rows)

            print 'Loading individual expenditures'
            self.load_individual_expenditures(year, tables[0], False)

            print 'Loading soliciation expenditures'
            self.load_individual_expenditures(year, tables[1], True)

            print 'Loading group expenditures'
            self.load_group_expenditures(year, tables[2])

            print ''

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
