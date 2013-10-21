var $search_form = $('.search form');
var $search_address = $('#address');
var $did_you_mean = $('.search .did-you-mean');
var $did_you_mean_list = $did_you_mean.find('ul');
var $not_found = $('.search .not-found');
var $search_loading = $('.search .loading');

var geocode_xhr = null;

function on_search_submit() {
    if ($search_address.val() === '') {
        return false;
    }

    $did_you_mean.hide();
    $not_found.hide();

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

                    alert(display_name);
                } else {
                    // If there are many results,
                    // show the did-you-mean path.
                    $did_you_mean_list.empty();

                    /*_.each(data, function(locale) {
                        locale['display_name'] = locale['display_name'].replace(', United States of America', '');
                        var context = $.extend(APP_CONFIG, locale);
                        var html = JST.did_you_mean_item(context);

                        $did_you_mean_list.append(html);
                    });*/

                    $did_you_mean.show();
                }
            }
        });
    } else {
        $not_found.show();
    }

    return false;
}

$(function() {
    $search_form.on('submit', on_search_submit);
});
