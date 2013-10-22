#!/usr/bin/env python

import json
from mimetypes import guess_type
import urllib

import envoy
from flask import Flask, Markup, abort, render_template
from peewee import fn

import app_config
import copytext
from models import Expenditure, Legislator, Lobbyist, Group, Organization
from render_utils import flatten_app_config, make_context

app = Flask(app_config.PROJECT_NAME)

# Example application views
@app.route('/')
def index():
    """
    Example view demonstrating rendering a simple HTML page.
    """
    context = make_context()

    expenditures = Expenditure.select()
    organizations = Organization.select()
    lobbyists = Lobbyist.select()
    legislators = Legislator.select()

    for legislator in legislators:
        legislator.total_spending = legislator.expenditures.aggregate(fn.Sum(Expenditure.cost))

    legislators_total_spending = sorted(legislators, key=lambda l: l.total_spending, reverse=True)[:10]
    
    categories_total_spending = {}

    for org in organizations:
        org.total_spending = org.expenditures.aggregate(fn.Sum(Expenditure.cost))

        if not org.total_spending:
            continue

        if org.category in categories_total_spending:
            categories_total_spending[org.category] += org.total_spending
        else:
            categories_total_spending[org.category] = org.total_spending

    organizations_total_spending = sorted(organizations, key=lambda o: o.total_spending, reverse=True)[:10]
    categories_total_spending = sorted(categories_total_spending.items(), key=lambda c: c[1], reverse=True)[:10]

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

@app.route('/legislators/<string:slug>/')
def _legislator(slug):
    """
    Legislator detail page.
    """
    context = make_context()

    legislators = Legislator.select()
    legislator = Legislator.get(Legislator.slug==slug)

    for l in legislators:
        l.total_spending = l.expenditures.aggregate(fn.Sum(Expenditure.cost))

    legislators_total_spending = sorted(legislators, key=lambda l: l.total_spending, reverse=True)
    
    legislator_rank = None

    for i, l in enumerate(legislators_total_spending):
        if l.id == legislator.id:
            legislator_rank = i + 1

    org_spending = {}

    for ex in legislator.expenditures:
        if ex.organization in org_spending:
            org_spending[ex.organization] += ex.cost
        else:
            org_spending[ex.organization] = ex.cost

    top_organizations = []

    for org, spending in org_spending.items():
        org.total_spending = spending
        top_organizations.append(org)

    top_organizations = sorted(top_organizations, key=lambda o: o.total_spending, reverse=True)[:10]

    context['legislator'] = legislator
    context['total_spending'] = sum([e.cost for e in legislator.expenditures]) 
    context['total_expenditures'] = legislator.expenditures.count()
    context['top_organizations'] = top_organizations 
    context['legislator_rank'] = legislator_rank

    return render_template('legislator.html', **context)

@app.route('/groups/<string:slug>/')
def _group(slug):
    """
    Group detail page.
    """
    context = make_context()

    groups = Group.select()
    group = Group.get(Group.slug==slug)

    for g in groups:
        g.total_spending = g.expenditures.aggregate(fn.Sum(Expenditure.cost))

    groups_total_spending = sorted(groups, key=lambda l: l.total_spending, reverse=True)
    
    group_rank = None

    for i, g in enumerate(groups_total_spending):
        if g.id == group.id:
            group_rank = i + 1

    org_spending = {}

    for ex in group.expenditures:
        if ex.organization in org_spending:
            org_spending[ex.organization] += ex.cost
        else:
            org_spending[ex.organization] = ex.cost

    top_organizations = []

    for org, spending in org_spending.items():
        org.total_spending = spending
        top_organizations.append(org)

    top_organizations = sorted(top_organizations, key=lambda o: o.total_spending, reverse=True)[:10]

    context['group'] = group 
    context['total_spending'] = sum([e.cost for e in group.expenditures]) 
    context['total_expenditures'] = group.expenditures.count()
    context['top_organizations'] = top_organizations 
    context['group_rank'] = group_rank

    return render_template('group.html', **context)


@app.route('/organization/<string:slug>/')
def _organization(slug):
    """
    Organization detail page.
    """
    context = make_context()
    
    organization = Organization.get(Organization.slug==slug)
    organizations = Organization.select()

    for o in organizations:
        o.total_spending = o.expenditures.aggregate(fn.Sum(Expenditure.cost))

    organizations_total_spending = sorted(organizations, key=lambda o: o.total_spending, reverse=True)
    
    organization_rank = None

    for i, o in enumerate(organizations_total_spending):
        if o.id == organization.id:
            organization_rank = i + 1

    legislator_spending = {}

    for ex in organization.expenditures:
        if ex.group:
            continue

        if ex.organization in legislator_spending:
            legislator_spending[ex.legislator] += ex.cost
        else:
            legislator_spending[ex.legislator] = ex.cost

    top_legislators = []

    for legislator, spending in legislator_spending.items():
        legislator.total_spending = spending
        top_legislators.append(legislator)

    top_legislators = sorted(top_legislators, key=lambda o: o.total_spending, reverse=True)[:10]

    context['organization'] = organization
    context['total_spending'] = sum([e.cost for e in organization.expenditures]) 
    context['total_expenditures'] = organization.expenditures.count()
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

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port')
    args = parser.parse_args()
    server_port = 8000

    if args.port:
        server_port = int(args.port)

    app.run(host='0.0.0.0', port=server_port, debug=app_config.DEBUG)
