#!/usr/bin/env python

import cStringIO
import datetime
import json
from mimetypes import guess_type
import urllib

from  csvkit.unicsv import  UnicodeCSVDictWriter
import envoy
from flask import Flask, Markup, abort, render_template, url_for
from peewee import fn

import app_config
import copytext
from models import Expenditure, Legislator, Lobbyist, Organization
from render_utils import flatten_app_config, make_context

app = Flask(app_config.PROJECT_NAME)

def get_ago():
    """
    Generate a datetime that will include 24 reporting periods
    for which we have data.
    """
    most_recent = Expenditure.select().order_by(Expenditure.report_period.desc()).limit(1)[0].report_period

    # Get the previous month. If previous month is December, set to 12. 
    month = most_recent.month + 1
    if month > 12: 
        month = 12

    ago = datetime.date(most_recent.year - 2, month, 1)

    return ago

@app.route('/')
def index():
    """
    Example view demonstrating rendering a simple HTML page.
    """
    context = make_context()

    ago = get_ago()

    expenditures = Expenditure.select().where(Expenditure.report_period >= ago)
    organizations = Organization.select().join(Expenditure).where(Expenditure.report_period >= ago).distinct()
    lobbyists = Lobbyist.select().join(Expenditure).where(Expenditure.report_period >= ago).distinct()
    legislators = Legislator.select().join(Expenditure).where(Expenditure.report_period >= ago).distinct()

    for legislator in legislators:
        legislator.total_spending = legislator.expenditures.where(Expenditure.report_period >= ago).aggregate(fn.Sum(Expenditure.cost))

    legislators_total_spending = sorted(legislators, key=lambda l: l.total_spending, reverse=True)[:10]
    
    categories_total_spending = {}

    for org in organizations:
        org.total_spending = org.expenditures.where(Expenditure.report_period >= ago).aggregate(fn.Sum(Expenditure.cost))

        if not org.total_spending:
            continue

        if org.category in categories_total_spending:
            categories_total_spending[org.category] += org.total_spending
        else:
            categories_total_spending[org.category] = org.total_spending

    organizations_total_spending = sorted(organizations, key=lambda o: o.total_spending, reverse=True)[:10]
    categories_total_spending = sorted(categories_total_spending.items(), key=lambda c: c[1], reverse=True)

    context['senators'] = Legislator.select().where(Legislator.office == 'Senator')
    context['representatives'] = Legislator.select().where(Legislator.office == 'Representative')
    context['expenditures'] = expenditures
    context['total_spending'] = expenditures.aggregate(fn.Sum(Expenditure.cost)) 
    context['total_expenditures'] = expenditures.count()
    context['total_organizations'] = organizations.count()
    context['total_lobbyists'] = lobbyists.count()
    context['organizations_total_spending'] = organizations_total_spending
    context['legislators_total_spending'] = legislators_total_spending
    context['categories_total_spending'] = categories_total_spending

    return render_template('index.html', **context)

@app.route('/legislators/')
def legislators():
    """
    Legislator list page.
    """
    context = make_context()

    senate_list = Legislator.select().where(Legislator.office == 'Senator')
    house_list = Legislator.select().where(Legislator.office == 'Representative')

    context['senate_list'] = senate_list
    context['house_list'] = house_list

    return render_template('legislator_list.html', **context)    

@app.route('/organizations/')
def organizations():
    """
    Legislator list page.
    """
    context = make_context()

    context['organizations'] = Organization.select().order_by(Organization.name)

    return render_template('organization_list.html', **context)    

@app.route('/methodology/')
def methodology():
    """
    Methodology explainer page.
    """
    context = make_context()

    return render_template('methodology.html', **context)

@app.route('/download/lobbyingmissouri.csv')
def download_csv():
    """
    Generate a data download.
    """
    f = cStringIO.StringIO()

    writer = UnicodeCSVDictWriter(f, [
        'lobbyist_first_name',
        'lobbyist_last_name',
        'report_period',
        'recipient_name',
        'recipient_type',
        'legislator_first_name',
        'legislator_last_name',
        'legislator_office',
        'legislator_party',
        'legislator_district',
        'event_date',
        'category',
        'description',
        'cost',
        'organization_name',
        'organization_industry',
        'group',
        'ethics_board_id',
        'is_solicitation'
    ])

    writer.writeheader()

    expenditures = Expenditure.select()

    for ex in expenditures:
        row = {
            'lobbyist_first_name': ex.lobbyist.first_name,
            'lobbyist_last_name': ex.lobbyist.last_name,
            'report_period': ex.report_period,
            'recipient_name': ex.recipient,
            'recipient_type': ex.recipient_type,
            'legislator_first_name': ex.legislator.first_name if ex.legislator else None,
            'legislator_last_name': ex.legislator.last_name if ex.legislator else None,
            'legislator_office': ex.legislator.office if ex.legislator else None,
            'legislator_party': ex.legislator.party if ex.legislator else None,
            'legislator_district': ex.legislator.district if ex.legislator else None,
            'event_date': ex.event_date,
            'category': ex.category,
            'description': ex.description,
            'cost': ex.cost,
            'organization_name': ex.organization.name,
            'organization_industry': ex.organization.category,
            'group': ex.group.name if ex.group else None,
            'ethics_board_id': ex.ethics_id,
            'is_solicitation': ex.is_solicitation
        }

        writer.writerow(row)

    return f.getvalue().decode('utf-8')

@app.route('/sitemap.xml')
def sitemap():
    """
    Renders a sitemap.
    """
    context = make_context()
    context['pages'] = []

    now = datetime.date.today().isoformat()

    context['pages'].append(('/', now))
    context['pages'].append(('/methodology/', now))
    context['pages'].append(('/legislators/', now))
    context['pages'].append(('/organizations/', now))

    for legislator in Legislator.select():
        context['pages'].append((url_for('_legislator', slug=legislator.slug), now))

    for organization in Organization.select():
        context['pages'].append((url_for('_organization', slug=organization.slug), now))

    sitemap = render_template('sitemap.xml', **context)

    return (sitemap, 200, { 'content-type': 'application/xml' })

@app.route('/promo.html')
def promo():
    """
    Promo page.
    """
    context = make_context()

    return render_template('promo.html', **context)


@app.route('/legislators/<string:slug>/')
def _legislator(slug):
    """
    Legislator detail page.
    """
    context = make_context()

    ago = get_ago()

    legislators = Legislator.select()
    legislator = Legislator.get(Legislator.slug==slug)

    for l in legislators:
        l.total_spending = l.expenditures.where(Expenditure.report_period >= ago).aggregate(fn.Sum(Expenditure.cost))

    legislators_total_spending = sorted(legislators, key=lambda l: l.total_spending, reverse=True)
    
    legislator_rank = None

    for i, l in enumerate(legislators_total_spending):
        if l.id == legislator.id:
            legislator_rank = i + 1

    org_spending = {}

    for ex in legislator.expenditures:
        if ex.organization.id in org_spending:
            org_spending[ex.organization.id] += ex.cost
        else:
            org_spending[ex.organization.id] = ex.cost

    top_organizations = []
    top_categories = {}

    for org_id, spending in org_spending.items():
        org = Organization.get(Organization.id == org_id)
        org.total_spending = spending
        top_organizations.append(org)

        if org.category in top_categories:
            top_categories[org.category] += org.total_spending
        else:
            top_categories[org.category] = org.total_spending

    top_organizations = sorted(top_organizations, key=lambda o: o.total_spending, reverse=True)[:10]
    top_categories = sorted(top_categories.items(), key=lambda c: c[1], reverse=True)

    context['legislator'] = legislator
    context['expenditures_recent'] = legislator.expenditures.where(Expenditure.report_period >= ago).order_by(Expenditure.cost.desc())
    context['total_spending'] = sum([e.cost for e in legislator.expenditures]) 
    context['total_spending_recent'] = sum([e.cost for e in legislator.expenditures.where(Expenditure.report_period >= ago)]) 
    context['total_expenditures'] = legislator.expenditures.count()
    context['total_expenditures_recent'] = legislator.expenditures.where(Expenditure.report_period >= ago).count()
    context['top_organizations'] = top_organizations 
    context['legislator_rank'] = legislator_rank
    context['top_categories'] = top_categories

    return render_template('legislator.html', **context)

@app.route('/organizations/<string:slug>/')
def _organization(slug):
    """
    Organization detail page.
    """
    context = make_context()

    ago = get_ago()
    
    organization = Organization.get(Organization.slug==slug)
    organizations = Organization.select().join(Expenditure).where(Expenditure.report_period >= ago).distinct()

    for o in organizations:
        o.total_spending = o.expenditures.where(Expenditure.report_period >= ago).aggregate(fn.Sum(Expenditure.cost))

    organizations_total_spending = sorted(organizations, key=lambda o: o.total_spending, reverse=True)
    
    organization_rank = None

    for i, o in enumerate(organizations_total_spending):
        if o.id == organization.id:
            organization_rank = i + 1

    legislator_spending = {}

    for ex in organization.expenditures:
        # Groups or old/non-attributable expenses
        if not ex.legislator:
            continue

        if ex.legislator.id in legislator_spending:
            legislator_spending[ex.legislator.id] += ex.cost
        else:
            legislator_spending[ex.legislator.id] = ex.cost

    top_legislators = []

    for legislator_id, spending in legislator_spending.items():
        legislator = Legislator.get(Legislator.id == legislator_id)
        legislator.total_spending = spending
        top_legislators.append(legislator)

    top_legislators = sorted(top_legislators, key=lambda o: o.total_spending, reverse=True)[:10]

    context['organization'] = organization
    context['expenditures_recent'] = organization.expenditures.where(Expenditure.report_period >= ago).order_by(Expenditure.cost.desc())
    context['total_spending'] = sum([e.cost for e in organization.expenditures]) 
    context['total_spending_recent'] = sum([e.cost for e in organization.expenditures.where(Expenditure.report_period >= ago)]) 
    context['total_expenditures'] = organization.expenditures.count()
    context['total_expenditures_recent'] = organization.expenditures.where(Expenditure.report_period >= ago).count()
    context['top_legislators'] = top_legislators 
    context['organization_rank'] = organization_rank

    return render_template('organization.html', **context)

# Render LESS files on-demand
@app.route('/less/<string:filename>')
def _less(filename):
    try:
        with open('less/%s' % filename) as f:
            less = f.read()
    except IOError:
        abort(404)

    r = envoy.run('node_modules/bin/lessc -', data=less)

    return r.std_out, 200, { 'Content-Type': 'text/css' }

# Render JST templates on-demand
@app.route('/js/templates.js')
def _templates_js():
    r = envoy.run('node_modules/bin/jst --template underscore jst')

    return r.std_out, 200, { 'Content-Type': 'application/javascript' }

# Render application configuration
@app.route('/js/app_config.js')
def _app_config_js():
    config = flatten_app_config()
    js = 'window.APP_CONFIG = ' + json.dumps(config)

    return js, 200, { 'Content-Type': 'application/javascript' }

# Render copytext
@app.route('/js/copy.js')
def _copy_js():
    copy = 'window.COPY = ' + copytext.Copy().json()

    return copy, 200, { 'Content-Type': 'application/javascript' }

# Server arbitrary static files on-demand
@app.route('/<path:path>')
def _static(path):
    try:
        with open('www/%s' % path) as f:
            return f.read(), 200, { 'Content-Type': guess_type(path)[0] }
    except IOError:
        abort(404)

@app.template_filter('urlencode')
def urlencode_filter(s):
    """
    Filter to urlencode strings.
    """
    if type(s) == 'Markup':
        s = s.unescape()

    s = s.encode('utf8')
    s = urllib.quote_plus(s)

    return Markup(s)

@app.template_filter('format_currency')
def format_currency(value):
    return "${:,.2f}".format(value)

@app.template_filter('format_currency_round')
def format_currency_round(value):
    return "${:,.0f}".format(value)

@app.template_filter('apnumber')
def apnumber(value):
    """
    Borrowed with love and adapted from django.contrib.humanize: https://github.com/django/django/blob/master/django/contrib/humanize/templatetags/humanize.py

    For numbers 1-9, returns the number spelled out. Otherwise, returns the
    number. This follows Associated Press style.
    """
    try:
        value = int(value)
    except (TypeError, ValueError):
        return value
    if not 0 <= value < 10:
        return value
    return ('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine')[value]

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port')
    args = parser.parse_args()
    server_port = 8000

    if args.port:
        server_port = int(args.port)

    app.run(host='0.0.0.0', port=server_port, debug=app_config.DEBUG)
