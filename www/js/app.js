var $search_form = $('.search form');
var $search_address = $('.search .address');
var $did_you_mean = $('.search .did-you-mean');
var $did_you_mean_list = $did_you_mean.find('ul');
var $not_found = $('.search .not-found');
var $search_loading = $('.search .loading');
var $search_results = $('.results');
var $rep_result = $('.results .rep');
var $sen_result = $('.results .sen');
var $search_examples = $('.search .example');
var $results_modal = $('#search-results');
var $modal_search_address = $results_modal.find('.address');
var $modal_not_found = $results_modal.find('.not-found');
var $modal_did_you_mean = $results_modal.find('.did-you-mean');
var $modal_did_you_mean_list = $modal_did_you_mean.find('ul');
var $modal_search_loading = $results_modal.find('.loading');
var $gift_table = $('.gift-table table');
var $gift_sort = $('#gift-sort');
var $show_senate_map = $('#show-senate-map');
var $show_house_map = $('#show-house-map');

var MISSOURI_EXTENTS = [-95.7747, 35.9957, -89.099, 40.6136];

var geocode_xhr = null;
var search_map = null;
    
var senate_layer = null;
var senate_grid = null;
var house_layer = null;
var house_grid = null;

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

    move_search_map(latitude, longitude);
    $results_modal.modal('show');

    return false;
}

function modal_is_visible() {
    return $results_modal.data('bs.modal') && $results_modal.data('bs.modal').isShown;
}

function on_search_submit() {
    if ($(this).find('input.address') === '') {
        return false;
    }

    var address = $(this).find('input.address').val();

    if (modal_is_visible()) {
        $modal_search_address.val(address);
    } else {
        $search_address.val(address);
    }

    $did_you_mean.hide();
    $not_found.hide();
    $search_results.hide();

    if (address) {
        if (modal_is_visible()) {
            $modal_search_loading.show();
        } else {
            $search_loading.show();
        }

        if (geocode_xhr) {
            geocode_xhr.abort();
        }

        geocode_xhr = $.ajax({
            'url': 'http://open.mapquestapi.com/nominatim/v1/search.php',
            'data': {
                'format': 'json',
                'json_callback': 'theCallback',
                'q': address,
                'viewbox': MISSOURI_EXTENTS.join(','),
                'bounded': 1
            },
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
                // Missouri addresses only.
                data = _.filter(data, function(locale) {
                    return locale['display_name'].indexOf('United States of America') > 0 && locale['display_name'].indexOf('Missouri') > 0;
                });

                $search_loading.hide();

                if (data.length === 0) {
                    // If there are no results, show a nice message.
                    if (modal_is_visible()) {
                        $modal_not_found.show();
                    } else {
                        $not_found.show();
                    }
                } else if (data.length == 1) {
                    // If there's one result, render it.
                    var locale = data[0];

                    var display_name = locale['display_name'].replace(', United States of America', '');

                    move_search_map(locale['lat'], locale['lon']);
                    on_show_senate_map_click();
                    
                    $results_modal.modal('show');
                    on_search_map_moveend();
                } else {
                    // If there are many resulits,
                    // show the did-you-mean path.
                    $did_you_mean_list.empty();

                    _.each(data, function(locale) {
                        locale['display_name'] = locale['display_name'].replace(', United States of America', '');
                        var context = $.extend(APP_CONFIG, locale);
                        var html = JST.did_you_mean(context);

                        $did_you_mean_list.append(html);
                    });

                    if (modal_is_visible()) {
                        $modal_did_you_mean.show();
                    } else {
                        $did_you_mean.show();
                    }
                }
            }
        });
    } else {
        if (modal_is_visible()) {
            $modal_not_found.show();
        } else {
            $not_found.show();
        }
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

function move_search_map(lat, lng) {
    search_map.setView([lat, lng], 10);
    //on_search_map_click({ latlng: new L.LatLng(lat, lng) });
}

function on_search_map_moveend(e) {
    var center = search_map.getCenter();

    senate_grid.getData(center, function(senate_data) {
        if (_.isUndefined(senate_data)) {
            $search_results.hide();
            return;
        }

        var sen_district = senate_data.DISTRICT;
        var sen = SENATORS[sen_district];
        $sen_result.html(JST.search_result(sen)); 

        house_grid.getData(center, function(house_data) {
            if (_.isUndefined(house_data)) {
                $search_results.hide();
                return;
            }

            var house_district = house_data.DISTRICT;
            var rep = REPRESENTATIVES[house_district];
            $rep_result.html(JST.search_result(rep)); 
        });

        $search_results.show();
    });

    return false;
}

function on_show_senate_map_click() {
    if ($show_senate_map.hasClass('btn-default')){
        $show_senate_map.toggleClass('btn-default btn-primary');
        $show_house_map.toggleClass('btn-default btn-primary');
    }
    search_map.removeLayer(house_layer);
    search_map.addLayer(senate_layer);

    return false;
}

function on_show_house_map_click() {
    if ($show_house_map.hasClass('btn-default')){
        $show_senate_map.toggleClass('btn-default btn-primary');
        $show_house_map.toggleClass('btn-default btn-primary');
    }
    search_map.removeLayer(senate_layer);
    search_map.addLayer(house_layer);

    return false;
}

$(function() {
    $search_form.on('submit', on_search_submit);
    $did_you_mean.on('click', 'li', on_did_you_mean_click);
    $search_examples.on('click', on_example_click);
    $gift_sort.on('change', on_gift_sort_change);

    $.tablesorter.addParser({ 
        id: 'hidden-text', 
        is: function(s) { 
            return false; 
        }, 
        format: function(s, table, cell, cellIndex) { 
            return $(cell).find('span').text();
        }, 
        type: 'text' 
    }); 

    $.tablesorter.addParser({ 
        id: 'hidden-number', 
        is: function(s) { 
            return false; 
        }, 
        format: function(s, table, cell, cellIndex) { 
            return parseFloat($(cell).find('span').text());
        }, 
        type: 'numeric' 
    }); 


    $gift_table.tablesorter({
        headers: {
            0: { sorter: 'hidden-text' },
            2: { sorter: 'hidden-number' }
        }
    });

    // Disable default sort events
    $gift_table.find('th').off();

    // make the header fixed on scroll
    $('.table-fixed-header').fixedHeader();

    // Load maps
    if ($('#search-map').length > 0) {
        search_map = L.mapbox.map('search-map', null, {
            minZoom: 6,
            maxZoom: 15
        });
        
        senate_layer = L.mapbox.tileLayer('http://a.tiles.mapbox.com/v3/npr.map-d0jcwmbw.json?3');
        senate_grid = L.mapbox.gridLayer('http://a.tiles.mapbox.com/v3/npr.map-d0jcwmbw.json?3');
        
        house_layer = L.mapbox.tileLayer('http://a.tiles.mapbox.com/v3/npr.map-bjum1mub.json?3');
        house_grid = L.mapbox.gridLayer('http://a.tiles.mapbox.com/v3/npr.map-bjum1mub.json?3');

        search_map.addLayer(senate_layer);
        search_map.addLayer(senate_grid);
        search_map.addLayer(house_grid);
        search_map.setView([36.46, -92.1], 7);
        search_map.scrollWheelZoom.disable();

        search_map.on('moveend', on_search_map_moveend);
        $show_senate_map.on('click', on_show_senate_map_click);
        $show_house_map.on('click', on_show_house_map_click);
    }
});

