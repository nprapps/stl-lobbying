#!/usr/bin/env python

import datetime
import re

import csvkit
from peewee import *
from playhouse.sqlite_ext import SqliteExtDatabase

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

class Legislator(SlugModel):
    """
    A legislator.
    """
    slug_fields = ['name']

    name = CharField()
    office = CharField()
    district = CharField()

class Organization(SlugModel):
    slug_fields = ['name']

    name = CharField()

class Expenditure(Model):
    """
    An expenditure.
    """
    lobbyist_name = CharField()
    report_period = DateField()
    recipient = CharField()
    recipient_type = CharField()
    legislator = ForeignKeyField(Legislator, related_name='expenditures', null=True)
    event_date = DateField()
    event_type = CharField()
    description =  CharField()
    cost = FloatField()
    organization = ForeignKeyField(Organization, related_name='expenditures')
    
    class Meta:
        database = database

def delete_tables():
    """
    Clear data from sqlite.
    """
    for cls in [Legislator, Organization, Expenditure]:
        try:
            cls.drop_table()
        except:
            continue

def create_tables():
    """
    Create database tables for each model.
    """
    for cls in [Legislator, Organization, Expenditure]:
        cls.create_table()

def load_legislator(name, office):
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
        district='' #TODO
    )

    legislator.save()

    return True, legislator

def load_organization(name):
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

def load_expenditures():
    """
    Load database tables from files.
    """
    SKIP_TYPES = ['Local Government Official', 'Public Official', 'ATTORNEY GENERAL', 'STATE TREASURER']

    with open('data/sample_data.csv') as f:
        reader = csvkit.CSVKitDictReader(f)
        rows = list(reader)

    i = 0
    expenditures = []
    warnings = []
    errors = []
    legislators_created = 0
    organizations_created = 0

    for row in rows:
        i += 1

        # Strip whitespace
        for k, v in row.items():
            row[k] = v.strip()

        # Report period
        report_period = datetime.datetime.strptime(row['Report'], '%b-%y').date()

        # Recipient
        recipient, recipient_type = row['Recipient'].split(' - ')

        # Legislator
        legislator = None
        created = False

        if recipient_type in ['Senator', 'Representative']:
            created, legislator = load_legislator(recipient, recipient_type)
        elif recipient_type in ['Employee or Staff', 'Spouse or Child']:
            # TODO
            pass
        elif recipient_type in SKIP_TYPES:
            warnings.append('%05i -- Skipping %s: %s' % (i, recipient_type, recipient))
            continue
        else:
            errors.append('%05i -- Unknown recipient type, "%s": %s' % (i, recipient_type, recipient))
            continue

        if created:
            legislators_created += 1

        # Event date
        bits = map(int, row['Date'].split('/'))
        event_date = datetime.date(bits[2], bits[0], bits[1])

        # Cost
        cost = float(row['Cost'].strip('()').strip('$'))

        # Organization
        created, organization = load_organization(row['Principal'])

        if created:
            organizations_created += 1

        # Create it!
        expenditures.append(Expenditure(
            lobbyist_name='%(Lob F Name)s %(Lob L Name)s' % row,
            lobbyist_last_name=row['Lob L Name'],
            report_period=report_period,
            recipient=recipient,
            recipient_type=recipient_type,
            legislator=legislator,
            event_date=event_date,
            event_type=row['Type'],
            description=row['Description'],
            cost=cost,
            organization=organization
        ))

    if warnings:
        print 'WARNINGS'
        print '--------'

        for warning in warnings:
            print warning

        print ''

    if errors:
        print 'ERRORS'
        print '------'

        for error in errors:
            print error

        return

    for expenditure in expenditures:
        expenditure.save()

    print 'SUMMARY'
    print '-------'

    print 'Processed %i rows' % i
    print 'Imported %i expenditures' % len(expenditures)
    print 'Created %i legislators' % legislators_created
    print 'Created %i organizations' % organizations_created
