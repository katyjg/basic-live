import requests
import csv
import time
import os
import pickle
from xml.dom import minidom
from pprint import pprint as print
import re
import itertools
from functools import reduce
import codecs
from datetime import date, datetime
from dateutil import parser
from collections import defaultdict
from django.conf import settings
from django.utils import dateparse, timezone
from django.db import transaction
from django.db.models import Subquery, OuterRef

from habanero import Crossref
from .multidict import MultiKeyDict
from . import models

PDB_FACILITY_ACRONYM = getattr(settings, 'PDB_FACILITY_ACRONYM', 'CLSI')
CONTACT_EMAIL = getattr(settings, 'CONTACT_EMAIL', 'cmcf-support@lightsource.ca')
CROSSREF_API_KEY =  getattr(settings, 'CROSSREF_API_KEY', None)
CROSSREF_THROTTLE = getattr(settings, 'CROSSREF_THROTTLE', 1)  # time delay between crossref calls
CROSSREF_BATCH_SIZE = getattr(settings, 'CROSSREF_THROTTLE', 10)
GOOGLE_API_KEY = getattr(settings, 'GOOGLE_API_KEY', None)


CROSSREF_EVENTS_URL = "https://api.eventdata.crossref.org/v1/events/distinct"
CROSSREF_CITATIONS_URL = "https://www.crossref.org/openurl/"
PDB_SEARCH_URL = getattr(settings, 'PDB_SEARCH_URL', "https://search.rcsb.org/rcsbsearch/v1/query")
PDB_REPORT_URL = getattr(settings, 'PDB_REPORT_URL', "https://data.rcsb.org/graphql")
GOOGLE_BOOKS_API = getattr(settings, 'GOOGLE_BOOKS_API', "https://www.googleapis.com/books/v1/volumes")
SCIMAGO_URL = getattr(settings, 'SCIMAGO_URL', "https://www.scimagojr.com/journalrank.php")

SEARCH_JSON = {
  "query": {
    "type": "terminal",
    "service": "text",
    "parameters": {
      "operator": "exact_match",
      "negation": False,
      "value": "{}".format(PDB_FACILITY_ACRONYM),
      "attribute": "diffrn_source.pdbx_synchrotron_site"
    }
  },
  "return_type": "entry",
  "request_options": {
    "return_all_hits": True
  }
}

REPORT_QUERY = """{{
  entries(entry_ids: [{0}]) {{
    rcsb_id
    struct {{
      title
    }}
    rcsb_accession_info {{
      initial_release_date
    }}
    pdbx_vrpt_summary {{
      PDB_deposition_date
      PDB_resolution
    }}
    diffrn_detector {{
      pdbx_collection_date
    }}
    diffrn_source {{
      pdbx_synchrotron_beamline
      pdbx_synchrotron_site
    }}
    rcsb_primary_citation {{
      rcsb_authors
      pdbx_database_id_DOI
      year
    }}
  }}
}}"""


def tag_function(entry):
    """
    Default tag function
    Given a PDB report entry, generate a list of tags to apply to the entry when created in the database.

    This function can be overridden through the PDB_TAG_FUNCTION settings variable
    :param entry:
    :return:
    """
    return [entry['diffrn_source.pdbx_synchrotron_beamline'].split()[-1],]

TAG_FUNCTION = getattr(settings, 'PDB_TAG_FUNCTION', tag_function)

def flatten(d, key=''):
    prefix = f'{key}.' if key else ''
    return (reduce(
        lambda new_d, kv: isinstance(kv[1], dict) and {**new_d, **flatten(kv[1], f'{prefix}{kv[0]}')} or {**new_d, f'{prefix}{kv[0]}': kv[1]},
            d.items(), {}))


class CrossRef(Crossref):
    def mentions(self, ids, year=None):
        ids = [ids] if isinstance(ids, str) else ids
        results = {}
        for key in ids:
            doi= key[4:] if key.lower().startswith('doi') else key
            params = {
                'mailto': self.mailto,
                'obj-id': doi,
                'rows': 0,
                #'facet': 'source:*'
            }
            if year:
                params['from-occurred-date'] = '{}-01-01'.format(year)
                params['until-occurred-date'] = '{}-12-31'.format(year)

            try:
                response = requests.get(CROSSREF_EVENTS_URL, params=params)
                response.raise_for_status()
            except requests.exceptions.HTTPError:
                print('Error fetching events for {}'.format(key))
            else:
                if 'json' in response.headers['Content-Type']:
                    info = response.json()
                    results[key] = info['message'].get('total-results', 0)
        return results

    def citations(self, ids):
        ids = [ids] if isinstance(ids, str) else ids
        results = {}
        for key in ids:
            params = {
                'pid': self.mailto,
                'id': "doi:{}".format(key[4:]),
                'noredirect': "true"
            }
            try:
                response = requests.get(CROSSREF_CITATIONS_URL, params=params)
                response.raise_for_status()
            except requests.exceptions.HTTPError:
                print('Error fetching events for {}'.format(key))
            else:
                if 'xml' in response.headers['Content-Type']:
                    xmldoc = minidom.parseString(response.content)
                    value = val = xmldoc.getElementsByTagName('query')[0].attributes['fl_count'].value
                    results[key] = int(value)
        return results


class ObjectParser(object):
    KEY_MAPS = {}
    FIELDS = []

    def __init__(self, entry):
        self._entry = entry

    def __getitem__(self, key):
        if isinstance(key, str):
            cleaner = 'get_{}'.format(key)
            if hasattr(self, cleaner):
                func = getattr(self, cleaner)
                return func()
            elif key in self.KEY_MAPS:
                return self._entry.get(self.KEY_MAPS[key])
            elif key in self._entry:
                return self._entry.get(key)
        else:
            raise TypeError("Invalid argument type.")

    def dict(self):
        return {
            field: self[field]
            for field in self.FIELDS
        }


class PDBParser(ObjectParser):
    """
    Used to extract Deposition specific data suitable for storing in the database
    from an RSCB API custom report entry

    """
    FIELDS = [
        'code', 'title', 'authors', 'doi', 'resolution',
        'released', 'deposited', 'collected', 'citation'
    ]
    KEY_MAPS = {
        'code': 'rcsb_id',
        'title': 'struct.title',
        'authors': 'rcsb_primary_citation.rcsb_authors',
        'resolution': 'pdbx_vrpt_summary.PDB_resolution',
        'collected': 'diffrn_detector.pdbx_collection_date'
    }

    def get_authors(self):
        return ', '.join(self._entry.get('rcsb_primary_citation.rcsb_authors', []))

    def get_released(self):
        return parser.isoparse(self._entry['rcsb_accession_info.initial_release_date'])

    def get_deposited(self):
        return parser.isoparse(self._entry['pdbx_vrpt_summary.PDB_deposition_date'])

    def get_collected(self):
        if self._entry.get('diffrn_detector.pdbx_collection_date'):
            return parser.isoparse(self._entry['diffrn_detector.pdbx_collection_date'])

    def get_doi(self):
        return "10.2210/pdb{}/pdb".format(self._entry['rcsb_id'].upper())

    def get_citation(self):
        if self._entry.get('rcsb_primary_citation.pdbx_database_id_DOI'):
            return 'DOI:{}'.format(self._entry['rcsb_primary_citation.pdbx_database_id_DOI'])

    def get_tags(self):
        return TAG_FUNCTION(self._entry)


class BookParser(ObjectParser):
    """
    Used to extract book specific data suitable for storing in the database
    from a Google books API report entry

    """
    FIELDS = ['published', 'authors', 'code', 'abstract', 'kind', 'title', 'publisher']
    BOOK_KIND = models.Publication.TYPES.book
    KEY_MAPS = {
        'abstract': 'description',
    }

    def get_code(self):
        return 'ISBN:{}'.format(self._entry['industryIdentifiers'][0]['identifier'])

    def get_published(self):
        if len(self._entry['publishDate']) ==4:
            return dateparse.parse_date('{}-01-01'.format(self._entry['publishDate']))
        elif len(self._entry['publishDate']) == 7:
            return dateparse.parse_date('{}-01'.format(self._entry['publishDate']))
        else:
            return dateparse.parse_date(self._entry['publishDate'])

    def get_kind(self):
        return self.BOOK_KIND

    def get_authors(self):
        return '; '.join(self._entry['authors'])

    def get_title(self):
        return '; '.join(
            filter(None, [
                self._entry['title'],
                self._entry.get('subtitle', '')
            ])
        )


class ArticleParser(ObjectParser):
    """
    Used to extra article specific data suitable for storing in the database
    from a CrossRef report entry

    """
    KEY_MAPS = {
        'topics': 'subject',
        'pages': 'page',
        'publisher': 'publisher',
    }

    FIELDS = [
        'published', 'authors', 'code', 'kind', 'title', 'publisher', 'volume', 'issue', 'pages'
    ]

    # map crossref work types to PublicationTypes
    TYPES_MAP = {
        'reference-book': models.Publication.TYPES.book,
        'proceedings-article': models.Publication.TYPES.proceeding,
        'dissertation': models.Publication.TYPES.phd_thesis,
        'edited-book': models.Publication.TYPES.book,
        'journal-article': models.Publication.TYPES.article,
        'report': models.Publication.TYPES.book,
        'book-track': models.Publication.TYPES.book,
        'standard': models.Publication.TYPES.book,
        'book-section': models.Publication.TYPES.chapter,
        'book-part': models.Publication.TYPES.chapter,
        'book': models.Publication.TYPES.book,
        'book-chapter': models.Publication.TYPES.chapter,
        'monograph': models.Publication.TYPES.book,
    }

    def get_code(self):
        return 'DOI:{}'.format(self._entry['DOI'])

    def get_published(self):
        """
        Generate a valid publish date, start with online, then hard and if not available,
        use the created date.

        :return: a date object
        """
        online = self._entry.get('published-online')
        hard = self._entry.get('published-print')
        created = self._entry.get('created')
        if online:
            parts = online['date-parts'][0]
        elif hard:
            parts = hard['date-parts'][0]
        else:
            parts = created['date-parts'][0]

        parts = parts + [1]*(3-len(parts))  # sometimes partial dates are given, assume first of month
        return date(*parts)

    def get_authors(self):
        return '; '.join([
            '{}, {}'.format(author['family'], author.get('given', ''))
            for author in self._entry['author']
        ])

    def get_kind(self):
        if self._entry['type'] == 'dissertation':
            degree = '; '.join(self._entry.get('degree'))
            if 'PhD' in degree or 'Doctor' in degree:
                return models.Publication.TYPES.phd_thesis
            elif 'MSc' in degree or 'Master' in degree:
                return models.Publication.TYPES.msc_thesis
            else:
                return models.Publication.TYPES.phd_thesis
        return self.TYPES_MAP.get(self._entry['type'], models.Publication.TYPES.magazine)

    def get_title(self):
        return '; '.join(self._entry['title'])

    def get_contributors(self):
        return [
            {
                'given_name': author['given'],
                'last_name': author['family']
            }
            for author in self._entry['author']
        ]

    def get_funders(self):
        return [
            {
                'name': funder['name'],
                'code': funder.get('DOI'),
            }
            for funder in self._entry.get('funder', [])
        ]

    def get_journal(self):
        issns = self._entry.get('ISSN', [])
        names = self._entry.get('short-container-title', [])
        names += self._entry.get('container-title', [])
        names.sort(key=lambda v: len(v))
        names = list(filter(None, names))
        if issns:
            return {
                'title': '; '.join(self._entry.get('container-title',[])),
                'codes': tuple(set(issns)),
                'publisher': self._entry.get('publisher'),
                'short_name': names[0]
            }

    def get_main_title(self):
        if self._entry['type'] in ['book-part', 'book-section', 'book-chapter']:
            return '; '.join(self._entry['container-title'])

    def get_isbn(self):
        return self._entry.get('ISBN', [])


class JournalParser(ObjectParser):
    """
    Used to extract journal specific data suitable for storing in the database
    from a CrossRef report entry

    """
    KEY_MAPS = {
        'publisher': 'publisher',
    }

    FIELDS = [
        'title', 'codes', 'publisher',
    ]

    def get_codes(self):
        return tuple(set(self._entry.get('ISSN', [])))

    def get_topics(self):
        return [topic['name'] for topic in self._entry.get('subjects', [])]

    def get_asjc(self):
        return list(filter(None, [topic.get('ASJC') for topic in self._entry.get('subjects', [])]))


class SCIMagoParser(ObjectParser):
    FIELDS = ['h_index', 'impact_factor', 'sjr_rank', 'sjr_quartile']

    @staticmethod
    def make_float(text):
        fixed_text = text.replace(',', '.')
        try:
            value = float(fixed_text)
        except ValueError:
            value = None
        return value

    def get_h_index(self):
        return self.make_float(self._entry['H index'])

    def get_impact_factor(self):
        return self.make_float(self._entry['Cites / Doc. (2years)'])

    def get_sjr_rank(self):
        return self.make_float(self._entry['SJR'])

    def get_sjr_quartile(self):
        return {
            'Q1': 1, 'Q2': 2, 'Q3': 3, 'Q4': 4
        }.get(self._entry['SJR Best Quartile'])

    def get_codes(self):
        return tuple({
            re.sub(r'(\w{4})(?!$)', r'\1-', code.strip())
            for code in self._entry['Issn'].split(',')
        })


def fetch_deposition_codes():
    """
    Retrieve all PDB Codes for the facility as a list of strings
    """
    response = requests.post(PDB_SEARCH_URL, json=SEARCH_JSON)

    if response.status_code == 200:
        return [entry['identifier'] for entry in response.json()['result_set']]
    else:
        response.raise_for_status()


def fetch_depositions(codes):
    """
    Fetch the CSV data for all specified PDB codes
    :param codes:  list of strings representing pdbcodes
    :return: a list of dictionaries one for each entry containing the report rows
    """

    params = REPORT_QUERY
    params = params.format(', '.join(['"{}"'.format(pdb) for pdb in codes]))

    response = requests.post(PDB_REPORT_URL, json={'query': params})

    if response.status_code == 200:
        return response.json()['data']['entries']
    else:
        response.raise_for_status()


def create_depositions(entries):
    """
    Create database entries for PDB results
    :param entries: list of dictionaries returned from PDB search reports
    :return: a dictionary representing the numbers of entries created or updated
    """

    no_refs = {
        obj.code: obj
        for obj in models.Deposition.objects.filter(reference__isnull=True, citation__isnull=True)
    }
    old_entries = models.Deposition.objects.values_list('code', flat=True)
    new_entries = {}
    updated_entries = []

    entry_tags = defaultdict(list)  # a list of tag names for each pdb code

    for entry in entries:
        for i, src in enumerate(entry['diffrn_source']):
            if src['pdbx_synchrotron_site'] == PDB_FACILITY_ACRONYM:
                break
        for k in ['diffrn_source', 'diffrn_detector']:
            entry[k] = entry.get(k) and entry.get(k, [])[i] or None
        entry = flatten(entry)
        record = PDBParser(entry)
        info = record.dict()
        if info['code'] in old_entries:
            # Update citation parameter if citation has changed
            if info['code'] in no_refs and info['citation'] and not no_refs[info['code']].citation:
                no_refs[info['code']].citation = info['citation']
                updated_entries.append(no_refs[info['code']])
        else:
            # New entries
            entry_tags[info['code']].extend(record['tags'])
            if not info['code'] in new_entries:   # entry will exist already for multi-beamline entries
                new_entries[info['code']] = models.Deposition(**info)

    # update old entries if any changes have happened
    if updated_entries:
        models.Deposition.objects.bulk_update(updated_entries, fields=['citation'])

    # create new entries if any
    if new_entries:
        models.Deposition.objects.bulk_create(new_entries.values())

    # now update tags
    name_tags = models.Tag.objects.in_bulk(field_name='name')    # maps tag names to tag
    all_tags = set(itertools.chain.from_iterable(entry_tags.values()))
    new_tags = all_tags - set(name_tags.keys())
    create_tags = [models.Tag(name=name) for name in new_tags]
    models.Tag.objects.bulk_create(create_tags)

    # Add new entries to name_tags
    name_tags.update(models.Tag.objects.in_bulk(new_tags, field_name='name'))

    # finally, add tag relationships to newly created deposition_entries:
    with transaction.atomic():
        for code, deposition in models.Deposition.objects.in_bulk(entry_tags.keys(), field_name='code').items():
            deposition.tags.set([name_tags[name] for name in entry_tags[code]])

    return {'created': len(new_entries), 'updated': len(updated_entries)}


def fetch_book(isbn_list):
    """
    Given a list of book ISBN numbers, return metadata for the first entry
    that successfully resolves using Google's Books API

    :param isbn_list: list of ISBN numbers
    :return: book parser
    """

    for isbn in isbn_list:
        isbn = re.sub(r'[\s_-]', '', isbn)
        params = {'q': 'isbn:{0}'.format(isbn), 'key': GOOGLE_API_KEY}
        response = requests.get(GOOGLE_BOOKS_API, params=params)
        if response.status_code == requests.codes.ok:
            result = response.json()
            if result['totalItems'] == 0:
                continue
            record = BookParser(result['items'][0]['volumeInfo'])
            return record


def chunker(iterable, n):
    """
    Iterate through an iteratable in junks of at most n items
    :param iterable: iterator
    :param n: number of items in each chunk
    :return: returns an iterable with n items
    """
    class Filler(object): pass
    return (
        itertools.filterfalse(lambda x: x is Filler, chunk)
        for chunk in (itertools.zip_longest(*[iter(iterable)]*n, fillvalue=Filler))
    )


def create_publications(doi_list):
    """
    Given a list of dois, create database entries for the publications
    :param doi_list:
    :return: a dictionary representing the numbers of entries created
    """

    existing_pubs = set(models.Publication.objects.values_list('code', flat=True))
    existing_journals = MultiKeyDict({
        codes: pk
        for codes, pk in models.Journal.objects.values_list('codes', 'pk')
    })

    # avoid fetching exising entries
    pending_dois = list(set(doi_list) - existing_pubs)

    if not pending_dois:
        return {'journals': 0, 'publications': 0}

    # fetch metadata from CrossRef
    cr = CrossRef(mailto=CONTACT_EMAIL, ua_string='MxLIVE')
    results = cr.works(ids=pending_dois)
    # fix inconsistent json from works
    results = results if isinstance(results, list) else [results]

    new_publications = {}   # details of publications to create indexed by doi code
    new_journals = MultiKeyDict({})  # journals to create

    # first pass to create publication details
    for item in results:
        entry = ArticleParser(item['message'])
        details = entry.dict()

        if details['code'] in existing_pubs:
            # publication exists already
            continue

        if details['kind'] == models.Publication.TYPES.chapter:
            book_entry = fetch_book(entry['isbn'])
            details['main_title'] = book_entry['title']
            details['editor'] = book_entry['authors']
            details['publisher'] = book_entry['publisher']
        elif details['kind'] == models.Publication.TYPES.book:
            book_entry = fetch_book(entry['isbn'])
            details.update(book_entry.dict())
        else:
            journal = entry['journal']
            if journal:
                codes = journal['codes']
                if codes in existing_journals:
                    details['journal_id'] = existing_journals[codes]
                else:
                    # add journal details to new journals to create
                    new_journals[codes] = journal

                # keep issn for later use to swap for journal_id
                details['journal_issn'] = codes

        new_publications[details['code']] = details

    # Fetch new journal entries
    for codes, journal in new_journals.items():
        found = False
        for code in codes:
            try:
                results = cr.journals(ids=code)
                found = True
            except requests.exceptions.HTTPError as e:
                continue

            # update journal details in new journals
            entry = JournalParser(results['message'])
            new_journals[codes].update(entry.dict())
            break

    # now ready to create journals
    to_create = MultiKeyDict({
        codes: models.Journal(**details) for codes, details in new_journals.items()
        if codes
    })

    models.Journal.objects.bulk_create(to_create.values())

    # update journal_ids
    existing_journals = MultiKeyDict({
        codes: pk
        for codes, pk in models.Journal.objects.values_list('codes', 'pk')
    })

    # update publication details
    for details in new_publications.values():
        if 'journal_issn' in details:
            details['journal_id'] = existing_journals[details.pop('journal_issn')]

    # create publication entries
    if new_publications:
        to_create = [
            models.Publication(**details)
            for details in new_publications.values()
        ]
        models.Publication.objects.bulk_create(to_create)

    return {'journals': len(new_journals), 'publications': len(new_publications)}


def fetch_and_update_depositions():
    """
    Fetch PDB Codes from RCSB, Create new entries, Update entries, create related
    Publication records and Journals, link everything together
    """

    now = timezone.now()

    # create PDB depositions
    codes = fetch_deposition_codes()
    entries = fetch_depositions(codes)
    create_depositions(entries)

    # update Publication information creating new ones if necessary
    pending_depositions = defaultdict(list)
    for deposition in models.Deposition.objects.filter(citation__isnull=False, reference__isnull=True):
        pending_depositions[deposition.citation].append(deposition)

    dois_pending = (
        doi[4:]
        for doi in pending_depositions.keys()
    )

    # process dois in chunks of CROSSREF_BATCH_SIZE, to avoid issues with CrossRef rate limits
    count = 0
    for chunk in chunker(dois_pending, CROSSREF_BATCH_SIZE):
        doi_list = list(chunk)
        count += len(doi_list)
        print('CREATING PUBLICATIONS: {}'.format(count))
        print(doi_list)
        create_publications(doi_list)
        time.sleep(CROSSREF_THROTTLE)

    # Update references
    added_references = models.Publication.objects.filter(created__gt=now).in_bulk(
            pending_depositions.keys(), field_name='code'
    )

    for code, depositions in pending_depositions.items():
        for deposition in depositions:
            deposition.reference = added_references.get(code)

    models.Deposition.objects.bulk_update([
        deposition
        for depositions in pending_depositions.values()
        for deposition in depositions
    ], fields=['reference'])


def fetch_journal_metrics(year=None):
    """
    Fetch Journal Metrics for a given year from SJR
    :param year: Year
    :return: a dictionary containing metrics keyed by journal ISSN number
    """

    params = {
        'out': 'xls',
        'year': year if year else timezone.now().year
    }

    file_path = os.path.join(settings.LOCAL_DIR, 'scimago-{}.pickle'.format(params['year']))
    if os.path.exists(file_path):
        with open(file_path, 'rb') as handle:
            return pickle.load(handle)
    else:
        response = requests.get(SCIMAGO_URL, params=params)
        if response.status_code == 200:
            dialect = csv.Sniffer().sniff(response.text[:5000])
            text = codecs.iterdecode(response.iter_lines(), 'utf-8')
            reader = csv.DictReader(text, dialect=dialect)
            results = {
                obj.get_codes(): obj.dict()
                for row in reader
                for obj in [SCIMagoParser(row)]
            }
            with open(file_path, 'wb') as handle:
                pickle.dump(results, handle)
            return results

        else:
            response.raise_for_status()


def update_journal_metrics(year=None):
    """
    Fetch and create journal metrics profile for current year or a given year
    :param year: Year or None
    :return: Number of profiles created and deleted
    """

    # fetch metrics for the year
    now = timezone.localtime(timezone.now())
    yr = year if year else now.year
    effective = datetime(yr, 1, 1, 12, 0, tzinfo=now.tzinfo)
    metrics = MultiKeyDict(fetch_journal_metrics(yr))

    # entries to be created
    to_create = [
        models.JournalProfile(owner=journal, effective=effective, **metrics[journal.codes])
        for journal in models.Journal.objects.filter(articles__published__year__lte=yr).distinct()
        if journal.codes in metrics
    ]

    # remove existing metrics for given year and replace with updated one.
    existing = models.JournalProfile.objects.filter(effective__year=yr)
    num_existing = existing.count()
    existing.delete()
    models.JournalProfile.objects.bulk_create(to_create)

    # Update Journals to point to latest metric
    newest = models.JournalProfile.objects.filter(owner=OuterRef('pk')).order_by('-effective')
    models.Journal.objects.update(metrics_id=Subquery(newest.values('pk')[:1]))

    return {'created': len(to_create), 'deleted': num_existing}


def fetch_article_metrics(doi, year=None):
    """
    Fetch article metrics for current year or a given year
    :param doi: Publication doi
    :param year: target Year or None for current year
    :return: dictionary of article metrics
    """

    cr = CrossRef(mailto=CONTACT_EMAIL, ua_string='MxLIVE')
    mentions = cr.citations(ids=doi)
    return mentions


def update_publication_metrics(year=None):
    """
    Fetch and create/or update publication metrics for current year or a given year
    :param year: target Year or None for current year
    :return: number of entries created or deleted
    """

    # fetch metrics for the year
    now = timezone.localtime(timezone.now())
    yr = year if year else now.year

    cr = CrossRef(mailto=CONTACT_EMAIL, ua_string='MxLIVE')
    publications = models.Publication.objects.filter(published__year=year).in_bulk(field_name='code')

    doi_list = list(publications.keys())
    citations = cr.citations(doi_list)
    mentions = cr.mentions(doi_list)

    to_create = [
        models.Metric(
            effective=now,
            owner=publications[code],
            citations=citations.get(code, 0),
            mentions=mentions.get(code, 0)
        ) for code in citations.keys()
    ]

    models.Metric.objects.bulk_create(to_create)

    # Update publication to point to most recent metrics
    newest = models.Metric.objects.filter(owner=OuterRef('pk')).order_by('-effective')
    models.Publication.objects.update(metrics_id=Subquery(newest.values('pk')[:1]))

    return {'created': len(to_create)}


def update_funders():
    publications = models.Publication.objects.filter(kind=models.Publication.TYPES.article, funders__isnull=True).in_bulk(
        field_name='code'
    )
    cr = CrossRef(mailto=CONTACT_EMAIL, ua_string='MxLIVE')

    count = 0
    total = len(publications)

    for code, pub in publications.items():
        doi = code[4:]
        results = cr.works(ids=[doi])
        entry = ArticleParser(results['message'])
        funders = entry.get_funders()
        pub.funders.set([
            models.Funder.objects.get_or_create(name=funder['name'], defaults={'code': funder['code']})[0]
            for funder in funders
        ])
        time.sleep(CROSSREF_THROTTLE)
        count += 1
        print('{:0.2%} {}/{}'.format(count/total, count, total))


