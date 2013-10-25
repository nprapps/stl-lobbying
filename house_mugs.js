var fs       = require('fs');
var request  = require('request');
var jsdom    = require('jsdom').jsdom;
 
var get = function(url, cb) {
  request(url, function (error, response, body) {
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


 
var url_base = "http://www.house.mo.gov/member.aspx";
var member_pages = [];

get(url_base, function(body) {
  createDocument(body, function(window) {
   
    // your scraper
    var $      = window.$;
    $('#ContentPlaceHolder1_gridMembers_DXMainTable td:first-child a').each(function(){

      var url = url_base + $(this).attr('href');
      get(url, function(body) {
        createDocument(body, function(window) {
         
          // your scraper
          var $      = window.$;
          var $img = $("#ContentPlaceHolder1_imgPhoto");
          var file = $img.attr('src');
          var name = $img.attr('alt').toLowerCase().replace(/ /gi, '_').replace(/\./gi,'');
          console.log(name);

          request(file).pipe(fs.createWriteStream(name + '.png'));

        });
      });
    });
  });
});




 

