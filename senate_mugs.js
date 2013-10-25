var fs       = require('fs');
var request  = require('request');
var jsdom    = require('jsdom').jsdom;
 
var get = function(url, cb) {
  request(url, function (error, response, body) {
    console.log(response.statusCode);
    if (!error && response.statusCode == 200) {
      cb(body, response);
    }
  });
};
 
var createDocument = function(html, cb) {
  var document = jsdom(html);
  var window   = document.createWindow();
  jsdom.jQueryify(window, cb);
};
 
var url_base = "http://www.senate.mo.gov/13info/SenateRoster.htm";
var member_pages = [];

get(url_base, function(body) {
  createDocument(body, function(window) {
   
    // your scraper
    var $      = window.$;
    $('table table td:first-child a').each(function(){

      var url = $(this).attr('href');
      get(url, function(body) {
        createDocument(body, function(window) {
         
          // your scraper
          var $      = window.$;
          var $img = $("#container div:first-child img");
          var file = $img.attr('src');
          console.log(file);
          var name = window.document.title.toLowerCase().replace(/ /gi, '_').replace(/\./gi,'');
          console.log(name);

          request(file).pipe(fs.createWriteStream(name + '.gif'));

        });
      });
    });
  });
});
