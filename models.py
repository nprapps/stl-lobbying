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
                attr = re.sub(r"[^\w\s]", '', attr)
                attr = re.sub(r"\s+", '-', attr)

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

class Legislator(SlugModel):
    """
    A legislator.
    """
    slug_fields = ['name']

    name = CharField()
    office = CharField()
    district = CharField()
    party = CharField()

    def url(self):
        return '%s/legislator/%s/' % (app_config.S3_BASE_URL, self.slug)

class Group(SlugModel):
    slug_fields = ['name']

    name = CharField()

class Organization(SlugModel):
    slug_fields = ['name']

    name = CharField()

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

    party_lookup = {}
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
        self.party_lookup_filename = 'data/party_lookup.csv'
        self.individual_data_filename = 'data/sample_data.csv'
        self.group_data_filename = 'data/sample_group_data.csv'

    def warn(self, msg):
        self.warnings.append(msg)

    def error(self, msg):
        self.errors.append(msg)

    def load_party_lookup(self):
        """
        Load lobbyist->party mapping from file.
        """
        with open(self.party_lookup_filename) as f:
            reader = csvkit.CSVKitReader(f, encoding='latin1')
            
            for row in reader:
                recipient = tuple(map(unicode.strip, row[0].rsplit(' - ', 1)))

                self.party_lookup[recipient] = row[1]

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


    def load_legislator(self, name, office, party):
        """
        Get or create a legislator.
        """
        try:
            return False, Legislator.get(Legislator.name==name, Legislator.office==office)
        except Legislator.DoesNotExist:
            pass

        legislator = Legislator(
            name=name,
            office=office,
            district='', #TODO
            party=party
        )

        legislator.save()

        return True, legislator

    def load_organization(self, name):
        """
        Get or create an organization.
        """
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

            # Recipient
            recipient, recipient_type = map(unicode.strip, row['Recipient'].rsplit(' - ', 1))

            # Legislator
            legislator = None
            created = False

            if recipient_type in ['Senator', 'Representative']:
                party = self.party_lookup.get((recipient, recipient_type), '')

                if not party:
                    self.error('%05i -- No matching party affiliation for "%s": "%s"' % (i, recipient_type, recipient))

                created, legislator = self.load_legislator(recipient, recipient_type, party)
            elif recipient_type in ['Employee or Staff', 'Spouse or Child']:
                legislator_name, legislator_type = map(unicode.strip, row['Pub Off'].rsplit(' - ', 1))

                if legislator_type in self.SKIP_TYPES:
                    self.warn('%05i -- Skipping "%s": "%s" for "%s": "%s"' % (i, recipient_type, recipient, legislator_type, legislator_name))
                    continue

                party = self.party_lookup.get((legislator_name, legislator_type), '')

                if not party:
                    self.error('%05i -- No matching party affiliation for "%s": "%s"' % (i, legislator_name, legislator_type))

                created, legislator = self.load_legislator(legislator_name, legislator_type, party)
            elif recipient_type in self.SKIP_TYPES:
                self.warn('%05i -- Skipping "%s": "%s"' % (i, recipient_type, recipient))
                continue
            else:
                self.error('%05i -- Unknown recipient type, "%s": "%s"' % (i, recipient_type, recipient))
                continue

            if created:
                self.legislators_created += 1

            # Event date
            bits = map(int, row['Date'].split('/'))
            event_date = datetime.date(bits[2], bits[0], bits[1])

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

            # Group
            created, group = self.load_group(row['Group'])

            if created:
                self.groups_created += 1

            # Event date
            bits = map(int, row['Date'].split('/'))
            event_date = datetime.date(bits[2], bits[0], bits[1])

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
        self.load_party_lookup()
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
