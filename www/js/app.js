var $search_form = $('.search form');
var $search_address = $('#address');
var $did_you_mean = $('.search .did-you-mean');
var $did_you_mean_list = $did_you_mean.find('ul');
var $not_found = $('.search .not-found');
var $search_loading = $('.search .loading');
var $search_results = $('.results');
var $rep_result = $('.results .rep');
var $sen_result = $('.results .sen');
var $search_examples = $('.search .example');
var $gift_table = $('.gift-table table');
var $gift_sort = $('#gift-sort');

var geocode_xhr = null;

var SENATE_TOPOJSON = null;
var HOUSE_TOPOJSON = null;

function lookup_district(topology, name, lat, lng) {
    var point = { 'type': 'Point', 'coordinates': [lng, lat] };
    var count = topology.objects[name].geometries.length;

    for (var i = 0; i < count; i++) {
        var feature = topojson.feature(topology, topology.objects[name].geometries[i]);
        var polygon = { 'type': 'Polygon', 'coordinates': feature.geometry.coordinates };

        if (gju.pointInPolygon(point, polygon) !== false) {
            return feature.properties.DISTRICT;
        }
    };

    return null;
}

function lookup_legislators(lat, lng) {
    var sen_district = lookup_district(SENATE_TOPOJSON, 'senate', lat, lng);

    if (sen_district === null) {
        $not_found.show();

        return;
    }
    
    var rep_district = lookup_district(HOUSE_TOPOJSON, 'house', lat, lng);

    var sen = SENATORS[sen_district];
    var rep = REPRESENTATIVES[rep_district];

    $rep_result.html(JST.search_result(rep)); 
    $sen_result.html(JST.search_result(sen)); 

    $search_results.show();
}

function on_example_click() {
    var address = $(this).text();
    $search_address.val(address);

    $search_form.submit();

    return false;
}

function on_did_you_mean_click() {
    var $this = $(this);
    var display_name = $this.data('display-name');
    var latitude = $this.data('latitude');
    var longitude = $this.data('longitude');

    $did_you_mean.hide();

    lookup_legislators(latitude, longitude);

    return false;
}

function on_search_submit() {
    if ($search_address.val() === '') {
        return false;
    }

    $did_you_mean.hide();
    $not_found.hide();
    $search_results.hide();

    var address = $search_address.val();

    if (address) {
        $search_loading.show();

        if (geocode_xhr) {
            geocode_xhr.cancel();
        }

        geocode_xhr = $.ajax({
            'url': 'http://open.mapquestapi.com/nominatim/v1/search.php?format=json&json_callback=theCallback&q=' + address,
            'type': 'GET',
            'dataType': 'jsonp',
            'cache': true,
            'jsonp': false,
            'jsonpCallback': 'theCallback',
            'contentType': 'application/json',
            'complete': function() {
                geocode_xhr = null;
            },
            'success': function(data) {
                // US addresses only, plzkthxbai.
                data = _.filter(data, function(locale) {
                    return locale['display_name'].indexOf("United States of America") > 0;
                });

                $search_loading.hide();

                if (data.length === 0) {
                    // If there are no results, show a nice message.
                    $not_found.show();
                } else if (data.length == 1) {
                    // If there's one result, render it.
                    var locale = data[0];

                    var display_name = locale['display_name'].replace(', United States of America', '');

                    lookup_legislators(locale['lat'], locale['lon']);
                } else {
                    // If there are many results,
                    // show the did-you-mean path.
                    $did_you_mean_list.empty();

                    _.each(data, function(locale) {
                        locale['display_name'] = locale['display_name'].replace(', United States of America', '');
                        var context = $.extend(APP_CONFIG, locale);
                        var html = JST.did_you_mean(context);

                        $did_you_mean_list.append(html);
                    });

                    $did_you_mean.show();
                }
            }
        });
    } else {
        $not_found.show();
    }

    return false;
}

function on_gift_sort_change() {
    var val = $(this).val();
    var sort = [];

    if (val == 'date') {
        sort = [[0, 1]];
    } else if (val == 'organization') {
        sort = [[1, 0]];
    } else if (val == 'cost') {
        sort = [[2, 1]];
    }

    $gift_table.trigger('sorton', [sort]);

    return false;
}

$(function() {
    $.getJSON('static-data/senate_0.2.topojson', function(data) {
        SENATE_TOPOJSON = data;
    });

    $.getJSON('static-data/house_0.1.topojson', function(data) {
        HOUSE_TOPOJSON = data;
    });

    $search_form.on('submit', on_search_submit);
    $did_you_mean.on('click', 'li', on_did_you_mean_click);
    $search_examples.on('click', on_example_click);
    $gift_sort.on('change', on_gift_sort_change);

    $gift_table.tablesorter();

    // Disable default sort events
    $gift_table.find('th').off();
});
