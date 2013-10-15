#!/usr/bin/env python

import datetime

import csvkit
from peewee import *
from playhouse.sqlite_ext import SqliteExtDatabase

database = SqliteExtDatabase('stl-lobbying.db')

def delete_tables():
    """
    Clear data from sqlite.
    """
    try:
        Expenditure.drop_table()
    except:
        pass

def create_tables():
    """
    Create database tables for each model.
    """
    Expenditure.create_table()

class Expenditure(Model):
    """
    A project.
    """
    lobbyist_name = CharField()
    report_period = DateField()
    recipient = CharField()
    recipient_type = CharField()
    recipient_official = CharField()
    recipient_official_type = CharField()
    event_date = DateField()
    event_type = CharField()
    description =  CharField()
    cost = FloatField()
    principal = CharField()
    
    class Meta:
        database = database

def load_data():
    """
    Load database tables from files.
    """
    with open('data/sample_data.csv') as f:
        reader = csvkit.CSVKitDictReader(f)
        rows = list(reader)

    i = 0

    for row in rows:
        for k, v in row.items():
            row[k] = v.strip()

        report_period = datetime.datetime.strptime(row['Report'], '%b-%y').date()

        recipient, recipient_type = row['Recipient'].split(' - ')

        if recipient_type in ['Senator', 'Representative']:
            recipient_official = recipient
            recipient_official_type = recipient_type
        else:
            # TODO
            recipient_official = ''
            recipient_official_type = ''

        bits = map(int, row['Date'].split('/'))
        event_date = datetime.date(bits[2], bits[0], bits[1])

        cost = float(row['Cost'].strip('()').strip('$'))

        Expenditure.create(
            lobbyist_name='%(Lob F Name)s %(Lob L Name)s' % row,
            lobbyist_last_name=row['Lob L Name'],
            report_period=report_period,
            recipient=recipient,
            recipient_type=recipient_type,
            recipient_official=recipient_official,
            recipient_official_type=recipient_official_type,
            event_date=event_date,
            event_type=row['Type'],
            description=row['Description'],
            cost=cost,
            principal=row['Principal']
        )

        i += 1

    print 'Imported %i expenditures' % i
