# coding: utf-8

import mimetypes
import re

from bs4 import BeautifulSoup
import requests

from . import exceptions, settings, utils


simple_url_re = re.compile(r'^https?://\[?\w', re.IGNORECASE)
simple_url_2_re = re.compile(r'^www\.|^(?!http)\w[^@]+\.(com|edu|gov|int|mil|net|org)$', re.IGNORECASE)


class Haul(object):
    """
    Haul
    """

    def __init__(self,
                 parser=settings.DEFAULT_PARSER,
                 finder_pipeline=settings.FINDER_PIPELINE,
                 propagator_pipeline=settings.PROPAGATOR_PIPELINE):

        self.parser = parser
        self.finder_pipeline = finder_pipeline
        self.propagator_pipeline = propagator_pipeline

        self.response = None # via Requests
        self.soup = None # via BeautifulSoup

        self._result = None

    def __repr__(self):
        return '<Haul [parser: %s]>' % (self.parser)

    @property
    def result(self):
        if not isinstance(self._result, HaulResult):
            self._result = HaulResult()

        return self._result

    def retrieve_url(self, url):
        """
        Use requests to fetch remote content
        """

        r = requests.get(url)

        if r.status_code >= 400:
            raise exceptions.RetrieveError(r.status_code)

        real_url = r.url
        content = r.content

        try:
            content_type = r.headers['Content-Type']
        except KeyError:
            content_type, encoding = mimetypes.guess_type(real_url, strict=False)

        self.response = r

        return content_type.lower(), content

    def parse_html(self, html):
        """
        Use BeautifulSoup to parse HTML / XML
        http://www.crummy.com/software/BeautifulSoup/bs4/doc/#specifying-the-parser-to-use
        """

        soup = BeautifulSoup(html, self.parser)

        title_tag = soup.find('title')
        self.result.title = title_tag.string if title_tag else None

        self.soup = soup

        return soup

    def start_finder_pipeline(self, *args, **kwargs):
        pipeline_input = {
            'soup': self.soup,
        }
        pipeline_output = pipeline_input.copy()

        for idx, name in enumerate(self.finder_pipeline):
            pipeline_output['pipeline_index'] = idx
            pipeline_output['pipeline_break'] = False

            finder_func = utils.module_member(name)
            output = finder_func(*args, **pipeline_output)
            pipeline_output.update(output)

            if pipeline_output['pipeline_break']:
                break

        # remove unnecessary items
        pipeline_output.pop('pipeline_index', None)
        pipeline_output.pop('pipeline_break', None)
        pipeline_output.pop('soup', None)

        self.result.finder_image_urls = pipeline_output.get('finder_image_urls', [])

        return self.result

    def start_propagator_pipeline(self, *args, **kwargs):
        pipeline_input = {
            'finder_image_urls': self.result.finder_image_urls,
        }
        pipeline_output = pipeline_input.copy()

        for idx, name in enumerate(self.propagator_pipeline):
            pipeline_output['pipeline_index'] = idx
            pipeline_output['pipeline_break'] = False

            propagator_func = utils.module_member(name)
            output = propagator_func(*args, **pipeline_output)
            pipeline_output.update(output)

            if pipeline_output['pipeline_break']:
                break

        # remove unnecessary items
        pipeline_output.pop('pipeline_index', None)
        pipeline_output.pop('pipeline_break', None)
        pipeline_output.pop('finder_image_urls', None)

        self.result.propagator_image_urls = pipeline_output.get('propagator_image_urls', [])

        return self.result

    # API
    def find_images(self, url_or_html, extend=False):
        url = None
        content = None

        if simple_url_re.match(url_or_html):
            url = url_or_html
            content_type, content = self.retrieve_url(url)
        else:
            content_type = 'text/html'
            content = url_or_html

        self.result.url = url
        self.result.content_type = content_type

        if 'text/html' in content_type:
            self.parse_html(content)

            self.start_finder_pipeline()

            if extend:
                self.start_propagator_pipeline()

        elif 'image/' in content_type:
            self.result.finder_image_urls = [str(self.response.url), ]

            if extend:
                self.start_propagator_pipeline()

        else:
            raise exceptions.ContentTypeNotSupported(content_type)

        return self.result


class HaulResult(object):
    """
    Result of Haul
    """

    def __init__(self):
        self.content_type = None
        self.url = None
        self.title = None
        self.finder_image_urls = []
        self.propagator_image_urls = []
        # self.finder_image_file = None
        # self.propagator_image_file = None

    def __repr__(self):
        return '<HaulResult [Content-Type: %s]>' % (self.content_type)

    @property
    def image_urls(self):
        """
        Combine finder_image_urls and propagator_image_urls,
        remove duplicate but keep order
        """

        all_image_urls = self.finder_image_urls[:]
        for image_url in self.propagator_image_urls:
            if not utils.in_ignorecase(image_url, all_image_urls):
                all_image_urls.append(image_url)

        return all_image_urls

    # @property
    # def image_file(self):
    #     if self.propagator_image_file:
    #         which = self.propagator_image_file
    #     elif self.finder_image_file:
    #         which = self.finder_image_file
    #     else:
    #         which = None

    #     return which

    def to_dict(self):
        return self.__dict__