from __future__ import print_function
import scrapy
from scrapy.utils.project import get_project_settings
# from ipdb import set_trace as debug
from youtube_history.items import YoutubeHistoryItem
from youtube_history.request_object_parser import ChromeRequest
from scrapy.http.cookies import CookieJar
from lxml import html
from youtube_history.cookie_import import parse_cookies
from bs4 import BeautifulSoup
import json
import string

class YoutubeHistorySpider(scrapy.Spider):
    my_base_url = 'https://www.youtube.com'
    start_url = my_base_url+'/feed/history'
    filename = "youtube_watch_history.html"

    nextlink_egg = 'data-uix-load-more-href="/browse_ajax?action_continuation'
    
    name = 'yth_spider'
    def __init__(self, *args, **kwargs):
        super(YoutubeHistorySpider, self).__init__(*args, **kwargs)
        settings = get_project_settings()
        hf = settings.get("CHROME_HEADERS_FILE")
        cj = settings.get("COOKIES_JSON")
        if hf:
            ch = ChromeRequest.from_file(hf)
            self.init_cookies = ch.cookies
        elif cj:
            with open (cj, 'r') as fh:
                cookies = parse_cookies(fh.read())
                self.init_cookies = cookies

        if not hasattr(self, "init_cookies"):
            raise ValueError("Need to specify 'CHROME_HEADERS_FILE' "+
                             "or 'COOKIES_JSON' in settings.")


    def start_requests(self):
        """
        This overide gets the first page with cookies.
        """
        yield scrapy.Request(self.start_url, cookies=self.init_cookies,
                              callback=self.parse_startpage)


    def parse_startpage(self, response):
        body = response.text
        next_uri = self.sub_parse_next_link(body)
        if body.find("viewable when signed out") != -1:
            print("\n"*2," No Sign In" ,"\n")
            raise scrapy.exceptions.CloseSpider(reason='Not signed in on first page')
        for i in self.sub_parse_video_entries(body):
            yield i
        if next_uri:
            yield self.next_request(next_uri, response)


    def sub_parse_next_link(self, page_contents):
        """parse for next history page link"""
        fstart = page_contents.find(self.nextlink_egg)
        next_uri = page_contents[fstart:].split('"', 2)
        if len(next_uri) == 3:
            return next_uri[1]
        else:
            return None


    def next_request(self, next_uri, response):
        """A wrapper around 'scrapy.Request' """
        return scrapy.Request(self.my_base_url+next_uri, cookies=self.init_cookies,
                                callback=self.parse)


    def parse(self, response):
        if (b'application/json' in response.headers['Content-Type']):
            jdat = json.loads(response.text)
            if ('load_more_widget_html' in jdat):
                next_uri = self.sub_parse_next_link(jdat['load_more_widget_html'])
                if jdat['load_more_widget_html'].find("viewable when signed out") != -1:
                    raise scrapy.exceptions.CloseSpider(
                           reason='Not signed in on subsequent json request.')

                next_uri = self.sub_parse_next_link(jdat['load_more_widget_html'])
                if next_uri:
                    yield self.next_request(next_uri, response)

            if ('content_html' in jdat):
                # content = jdat['content_html']
                content = response.text
                for i in self.sub_parse_video_entries(content):
                    yield i
            else:
                raise scrapy.exceptions.CloseSpider(
                           reason='No history content returned on json request.')

    def date_parsing(self, datestring):
        # Date string is converted from MMM DD, YYYY to MM/DD/YYYY
        # TODO: Handle the parsing for upto one week prior to scraping date which is in the format of Tuesday, Friday, etc
        if "Jan" in datestring:
            formatteddate = "01"
        if "Feb" in datestring:
            formatteddate = "02"
        if "Mar" in datestring:
            formatteddate = "03"
        if "Apr" in datestring:
            formatteddate = "04"
        if "May" in datestring:
            formatteddate = "05"
        if "Jun" in datestring:
            formatteddate = "06"
        if "Jul" in datestring:
            formatteddate = "07"
        if "Aug" in datestring:
            formatteddate = "08"
        if "Sep" in datestring:
            formatteddate = "09"
        if "Oct" in datestring:
            formatteddate = "10"
        if "Nov" in datestring:
            formatteddate = "11"
        if "Dec" in datestring:
            formatteddate = "12"
        # TODO: make more readable version
        formatteddate = string.join([formatteddate, string.join(string.split(datestring[4:],", "), "/")],"/")
        return formatteddate

    def sub_parse_video_entries(self, page_contents):
        """Does the actual data extraction"""
        historypage = BeautifulSoup(page_contents, "lxml")
        print(len(historypage))
        # Select the individual days which are contained inside the ytd-item-section-renderer
        watchdays = historypage.select("ytd-item-section-renderer")
        # print(type(watchdays))
        # print(len(watchdays))
        print(historypage)
        for day in watchdays:
            # Only parse days with valid video entries
            print("here")
            print(type(day))
            if len(day) > 1:
                datestring = day.select("div[id='title'].ytd-item-section-header-renderer")[0].getText()
                date = self.date_parsing(datestring)
                # Create a list of all videos for the current "day" and fill in the appropriate fields
                vidlist = day.select("div[id='dismissable']")
                for video in vidlist:
                    hitem = YoutubeHistoryItem()
                    hitem['date'] = date
                    print(date)
                    titletag = video.select("a[id='video-title']")[0]
                    hitem['title'] = titletag.getText().strip()
                    hitem['vid'] = titletag['href']
                    channeltag = video.select("yt-formatted-string>a.yt-simple-endpoint")[0]
                    hitem['channel'] = channeltag.getText()
                    hitem['channel_url'] = channeltag['href']
                    hitem['description'] = video.select("yt-formatted-string[id='description-text']")[0].getText()
                    hitem['time'] = video.select("span.ytd-thumbnail-overlay-time-status-renderer")[0].getText()
                    print(hitem)
                    yield hitem