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
    lobbyist_first_name = CharField()
    lobbyist_last_name = CharField()
    report_period = DateField()
    recipient = CharField()
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
        report_period = datetime.datetime.strptime(row['Report'].strip(), '%b-%y').date()

        bits = map(int, row['Date'].strip().split('/'))
        event_date = datetime.date(bits[2], bits[0], bits[1])

        cost = float(row['Cost'].strip('()').strip('$').strip())

        Expenditure.create(
            lobbyist_first_name=row['Lob F Name'].strip(),
            lobbyist_last_name=row['Lob L Name'].strip(),
            report_period=report_period,
            recipient=row['Recipient'].strip(),
            event_date=event_date,
            event_type=row['Type'].strip(),
            description=row['Description'].strip(),
            cost=cost,
            principal=row['Principal'].strip()
        )

        i += 1

    print 'Imported %i expenditures' % i
