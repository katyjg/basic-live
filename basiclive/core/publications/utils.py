import csv
import itertools
import operator
import pickle
import re
import time
from collections import defaultdict
from datetime import date, timedelta
from datetime import datetime
from functools import reduce, lru_cache
from itertools import batched
from pathlib import Path
from pprint import pprint as print

import httpx2
import pandas as pd
from django.conf import settings as main_settings
from django.db import transaction
from django.db.models import Q
from django.utils import dateparse, timezone
from habanero import Crossref
from habanero.exceptions import RequestError as HabaneroRequestError

from basiclive.core.publications.conf import settings
from . import models
from .multidict import MultiKeyDict


def get_search_json():
    return {
        "query": {
            "type": "terminal",
            "service": "text",
            "parameters": {
                "operator": "exact_match",
                "negation": False,
                "value": f"{settings.PDB_FACILITY_ACRONYM}",
                "attribute": "diffrn_source.pdbx_synchrotron_site"
            }
        },
        "return_type": "entry",
        "request_options": {
            "return_all_hits": True
        }
    }


SEARCH_JSON = get_search_json()

REPORT_QUERY = """{{
  entries(entry_ids: [{0}]) {{
    rcsb_id
    struct {{
      title
    }}
    rcsb_accession_info {{
      initial_release_date
      deposit_date
    }}
    rcsb_entry_info {{
      diffrn_resolution_high {{
        provenance_source
        value
      }}
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



def flatten(d, parent_key='') -> dict:
    """
    Flattens a nested dictionary, concatenating keys with dots.

    :param d: The dictionary to flatten.
    :param parent_key: The prefix for keys (used in recursion).
    :return: A flat dictionary with dot-separated keys.
    """
    items = {}
    for k, v in d.items():
        new_key = f"{parent_key}.{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten(v, new_key))
        else:
            items[new_key] = v
    return items


class CrossRef(Crossref):
    def __init__(self):
        super().__init__(mailto=settings.CONTACT_EMAIL, ua_string='BasicLIVE')

    def mentions(self, doi, year=None):
        headers = {
            'Accept': 'application/json',
        }
        params = {
            'mailto': self.mailto,
            'obj-id': doi,
            'rows': 1000,
        }
        if year:
            params['from-occurred-date'] = f'{year}-01-01'
            params['until-occurred-date'] = f'{year}-12-31'

        events = []
        more_results = True
        while more_results:
            response = httpx2.get(settings.CROSSREF_EVENTS_URL, params=params, headers=headers, follow_redirects=True, timeout=30.0)
            if response.status_code == 200:
                result = response.json()
                message = result.get('message', {})
                new_events = message.get('events', [])
                events.extend(new_events)
                total_events = message.get('total-results', 0)
                more_results = len(new_events) and (len(events) < total_events)
                params['cursor'] = message.get('next-cursor', None)
            else:
                more_results = False
        if not events:
            return {}

        df = pd.DataFrame(events)
        df['year'] = df.timestamp.str[:4]
        mentions = df.groupby('year').size().to_dict()

        if year:
            # if year is specified, return only that year
            return mentions.get(str(year), 0)
        return mentions


class OpenCitations:
    def __init__(self, api_key=None, rate_limit=10):
        self.rate_limit = rate_limit
        self.api_key = api_key or settings.OPEN_CITATIONS_KEY
        self.base_url = settings.OPEN_CITATIONS_URL
        self.headers = {
            'Accept': 'application/json',
            'authorization': self.api_key,
        }

    def citations_list(self, doi, year: int = None) -> list[dict]:
        """
        Get the list of citations for a given DOI from OpenCitations API.

        :param doi: The DOI of the publication.
        :param year: Optional year to filter results by.
        :return: Citations as a list of dicts
        """
        filters = f'?filter=creation={year}' if year else ''
        url = f"{self.base_url}citations/doi:{doi}{filters}"
        response = httpx2.get(url, headers=self.headers, follow_redirects=True, timeout=30.0)
        if response.status_code == 200:
            data = response.json()
            return data
        else:
            print(f"Error fetching citations for {doi}: {response.status_code}")
            return []

    def citations(self, doi, year: int = None) -> dict:
        """
        Get the number of citations for a given DOI from OpenCitations API.
        :param doi: The DOI of the publication.
        :param year: Optional year to filter results by.
        :return: dictionary mapping a year to a dictionary containing the number of citations
        """
        citations = self.citations_list(doi, year=year)
        if not citations:
            return {}

        df = pd.DataFrame(citations)
        df['year'] = df.creation.str[:4]
        all_cites = df.groupby('year').size().to_dict()
        self_cites = df.loc[df['author_sc'] == 'yes'].groupby('year').size().to_dict()
        years = set(all_cites.keys()).union(set(self_cites.keys()))
        info = {
            yr: {
                'citations': all_cites.get(yr, 0),
                'self_cites': self_cites.get(yr, 0)
            }
            for yr in sorted(years)
        }
        if year:
            # if year is specified, return only that year
            return info.get(str(year), {'citations': 0, 'self_cites': 0})
        return info


class ObjectParser(object):
    KEY_MAPS = {}
    FIELDS = []

    def __init__(self, entry):
        self._entry = entry

    def __getitem__(self, key):
        if isinstance(key, str):
            cleaner = f'get_{key}'
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
        'resolution': 'rcsb_entry_info.diffrn_resolution_high.value',
        'collected': 'diffrn_detector.pdbx_collection_date'
    }

    def get_authors(self):
        return ', '.join(self._entry.get('rcsb_primary_citation.rcsb_authors', []))

    def get_released(self):
        return datetime.fromisoformat(self._entry['rcsb_accession_info.initial_release_date'])

    def get_deposited(self):
        return datetime.fromisoformat(self._entry['rcsb_accession_info.deposit_date'])

    def get_collected(self):
        if self._entry.get('diffrn_detector.pdbx_collection_date'):
            return datetime.fromisoformat(self._entry['diffrn_detector.pdbx_collection_date'])

    def get_doi(self):
        return f"10.2210/pdb{self._entry['rcsb_id'].upper()}/pdb"

    def get_citation(self):
        if self._entry.get('rcsb_primary_citation.pdbx_database_id_DOI'):
            return f"DOI:{self._entry['rcsb_primary_citation.pdbx_database_id_DOI']}"

    def get_tags(self):
        return settings.PDB_TAG_FUNCTION(self._entry)


class BookParser(ObjectParser):
    """
    Used to extract book specific data suitable for storing in the database
    from a Google books API report entry

    """
    FIELDS = ['published', 'author_names', 'code', 'abstract', 'kind', 'title', 'publisher']
    BOOK_KIND = models.Publication.TYPES.book
    KEY_MAPS = {
        'abstract': 'description',
        'author_names': 'authors'
    }

    def get_code(self):
        return 'ISBN:{}'.format(self._entry['industryIdentifiers'][0]['identifier'])

    def get_published(self):
        if len(self._entry['publishDate']) == 4:
            return dateparse.parse_date(f'{self._entry["publishDate"]}-01-01')
        elif len(self._entry['publishDate']) == 7:
            return dateparse.parse_date(f'{self._entry["publishDate"]}-01')
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
        'published', 'author_names', 'code', 'kind', 'title',
        'publisher', 'volume', 'issue', 'pages',
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
        return f'DOI:{self._entry["DOI"]}'

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

    def get_author_names(self):
        return '; '.join([
            f'{author["family"]}, {author.get("given", "")}'
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

    @lru_cache(maxsize=128)
    def get_journal(self):
        codes = tuple(set(fix_issns(self._entry.get('ISSN', []))))
        names = self._entry.get('short-container-title', [])
        names += self._entry.get('container-title', [])
        names.sort(key=lambda v: len(v))
        names = list(filter(None, names))
        issn_query = reduce(operator.__or__, [Q(codes__icontains=issn) for issn in codes], Q())
        journal = models.Journal.objects.filter(issn_query).distinct().first()
        if journal:
            return journal.pk
        elif codes:
            return {
                'title': '; '.join(self._entry.get('container-title', [])),
                'codes': tuple(set(codes)),
                'publisher': self._entry.get('publisher'),
                'short_name': names[0]
            }

    def get_main_title(self):
        if self._entry['type'] in ['book-part', 'book-section', 'book-chapter']:
            return '; '.join(self._entry['container-title'])
        return None

    def get_isbn(self):
        return self._entry.get('ISBN', [])


def fix_issns(issns: list) -> list:
    """
    Fix issn formatting
    :param issns: list of strings
    :return: list of strings with issns formatted correctly
    """

    return [
        re.sub(r'(\w{4})(?!$)', r'\1-', issn.replace('-', '').strip())
        for issn in issns
    ] or []


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
        return tuple(set(fix_issns(self._entry.get('ISSN', []))))

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
        return self.make_float(
            self._entry.get('Cites / Doc. (2years)', self._entry.get('Citations / Doc. (2years)'))
        )

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


class AuthorParser(ObjectParser):
    """
    Used to extract author-specific data suitable for storing in the database
    from a CrossRef report entry

    """
    FIELDS = ['last_name', 'other_names', 'orcid']
    KEY_MAPS = {
        'last_name': 'family',
        'other_names': 'given',
        'orcid': 'ORCID'
    }


class AffiliationParser(ObjectParser):
    """
    Used to extract affiliation-specific data suitable for storing in the database
    from a CrossRef report entry

    """
    FIELDS = ['description', 'code']

    def get_description(self):
        description = []
        if 'name' in self._entry:
            description.append(self._entry['name'])
        if 'department' in self._entry:
            if isinstance(self._entry['department'], str):
                description.append(self._entry['department'])
            elif isinstance(self._entry['department'], list):
                description.extend(self._entry['department'])
        if 'address' in self._entry:
            description.append(self._entry['address'])
        if 'place' in self._entry:
            if isinstance(self._entry['place'], str):
                description.append(self._entry['place'])
            elif isinstance(self._entry['place'], list):
                description.extend(self._entry['place'])

        return ', '.join(description)

    def get_code(self):
        if 'id' in self._entry:
            if isinstance(self._entry['id'], str):
                return self._entry['id']
            elif isinstance(self._entry['id'], list) and 'id' in self._entry['id'][0]:
                return self._entry['id'][0]['id']
        return None


def fetch_deposition_codes():
    """
    Retrieve all PDB Codes for the facility as a list of strings
    """
    response = httpx2.post(settings.PDB_SEARCH_URL, json=get_search_json(), timeout=30.0)

    if response.status_code == 200:
        return [entry['identifier'] for entry in response.json()['result_set']]
    else:
        response.raise_for_status()


def fetch_depositions(codes) -> list[dict]:
    """
    Fetch the CSV data for all specified PDB codes
    :param codes:  list of strings representing pdbcodes
    :return: a list of dictionaries one for each entry containing the report rows
    """

    params = REPORT_QUERY
    params = params.format(', '.join([f'"{pdb}"' for pdb in codes]))

    response = httpx2.post(settings.PDB_REPORT_URL, json={'query': params}, timeout=30.0)
    if response.status_code == 200:
        result = response.json()
        return result['data']['entries']
    else:
        response.raise_for_status()
        return []


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
            if src['pdbx_synchrotron_site'] == settings.PDB_FACILITY_ACRONYM:
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
        params = {'q': 'isbn:{0}'.format(isbn), 'key': settings.GOOGLE_API_KEY}
        response = httpx2.get(settings.GOOGLE_BOOKS_API, params=params, follow_redirects=True, timeout=30.0)
        if response.status_code == httpx2.codes.OK:
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
    cr = CrossRef()
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
            if isinstance(journal, dict):
                codes = journal['codes']
                if codes in existing_journals:
                    details['journal_id'] = existing_journals[codes]
                else:
                    # add journal details to new journals to create
                    new_journals[codes] = journal

                # keep issn for later use to swap for journal_id
                details['journal_issn'] = codes
            elif isinstance(journal, int):
                details['journal_id'] = journal

        new_publications[details['code']] = details

    # Fetch new journal entries
    for codes, journal in new_journals.items():
        found = False
        for code in codes:
            try:
                results = cr.journals(ids=code)
                found = True
            except (HabaneroRequestError, httpx2.HTTPError) as e:
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
    existing_codes = set(models.Deposition.objects.values_list('code', flat=True))
    codes = fetch_deposition_codes()
    codes = list(set(codes) - existing_codes)

    for chunk in batched(codes, 100):
        entries = fetch_depositions(chunk)
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
    for chunk in chunker(dois_pending, settings.CROSSREF_BATCH_SIZE):
        doi_list = list(chunk)
        count += len(doi_list)
        print(f'Creating Publications: ...{count}')
        create_publications(doi_list)
        time.sleep(settings.CROSSREF_THROTTLE)

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
        'year': year - 1 if year else timezone.now().year - 1   # SJR reports are published for the previous year
    }
    cache_dir = Path(main_settings.LOCAL_DIR) / 'cache'
    cache_dir.mkdir(parents=True, exist_ok=True)
    file_path = cache_dir / f'scimago-{params["year"]}.pickle'
    csv_file = cache_dir / f'scimago-{params["year"]}.csv'

    if file_path.exists():
        with open(file_path, 'rb') as handle:
            return pickle.load(handle)
    elif csv_file.exists():
        print(f'Fetching journal metrics for {params["year"]} from SCIMAGO CSV...')
        with open(csv_file, 'r', encoding='utf-8') as handle:
            dialect = csv.Sniffer().sniff(handle.read(5000))
            handle.seek(0)
            reader = csv.DictReader(handle, dialect=dialect)
            results = {
                obj.get_codes(): obj.dict()
                for row in reader
                for obj in [SCIMagoParser(row)]
            }
            with open(file_path, 'wb') as handle:
                pickle.dump(results, handle)
            return results
    else:
        print(f'Fetching journal metrics for {params["year"]} from SCIMAGO...')
        response = httpx2.get(settings.SCIMAGO_URL, params=params, follow_redirects=True, timeout=30.0)
        if response.status_code == 200:
            dialect = csv.Sniffer().sniff(response.text[:5000])
            reader = csv.DictReader(response.iter_lines(), dialect=dialect)
            results = {
                obj.get_codes(): obj.dict()
                for row in reader
                for obj in [SCIMagoParser(row)]
            }
            with open(file_path, 'wb') as handle:
                pickle.dump(results, handle)
            return results


def update_journal_metrics(year=None):
    """
    Fetch and create journal metrics profile for current year or a given year
    :param year: Year or None
    :return: Number of profiles created and deleted
    """

    # fetch metrics for the year
    now = timezone.localtime(timezone.now())
    yr = year if year else now.year
    metrics_data = fetch_journal_metrics(yr)
    if not metrics_data:
        return {'created': 0, 'updated': 0}

    metrics = MultiKeyDict(metrics_data)

    # entries to be created
    target_journals = models.Journal.objects.filter(articles__published__year__lte=yr)
    to_create = [
        models.JournalMetric(journal=journal, year=yr, **metrics[tuple(journal.codes)])
        for journal in target_journals.exclude(metrics__year=yr).distinct()
        if tuple(journal.codes) in metrics
    ]
    models.JournalMetric.objects.bulk_create(to_create, batch_size=100)

    # entries to update
    print(f'Updating journal metrics for {yr}...')
    to_update = models.JournalMetric.objects.filter(year=yr, journal__in=target_journals).distinct('journal')
    num_updated = 0
    for metric in to_update:
        codes = tuple(metric.journal.codes)
        if codes in metrics:
            metric.h_index = metrics[codes]['h_index']
            metric.impact_factor = metrics[codes]['impact_factor']
            metric.sjr_rank = metrics[codes]['sjr_rank']
            metric.sjr_quartile = metrics[codes]['sjr_quartile']
            metric.modified = now
            num_updated += 1
    models.JournalMetric.objects.bulk_update(
        to_update, fields=['h_index', 'impact_factor', 'sjr_rank', 'sjr_quartile', 'modified']
    )

    # Update
    return {'created': len(to_create), 'updated': num_updated}


def fetch_article_metrics(doi, year=None):
    """
    Fetch article metrics for current year or a given year
    :param doi: Publication doi
    :param year: target Year or None for current year
    :return: dictionary of article metrics
    """

    cr = CrossRef()
    mentions = cr.citations(ids=doi)
    return mentions


def update_publication_metrics(rate_limit=10):
    """
    Fetch and create/or update publication metrics for current year or a given year

    :param rate_limit: maximum number of requests per second
    :return: number of entries created or deleted
    """

    # fetch metrics for the year
    now = timezone.localtime(timezone.now())
    cr = CrossRef()
    oc = OpenCitations()

    # Update metrics for publications that have no metrics or have not been updated in the last month
    last_month = now - timedelta(weeks=4)
    target_publications = models.Publication.objects.filter(code__regex=r'^DOI:10\.').filter(
        Q(metrics__isnull=True) | Q(metrics__modified__lte=last_month)
    )

    publications = target_publications.distinct('code').in_bulk(field_name='code')

    # Process at most CROSSREF_BATCH_SIZE publications at a time
    doi_list = list(publications.keys())
    to_create = []
    update_count = 0
    for code in doi_list:
        doi = code[4:]
        pub = publications.get(code)
        citations = oc.citations(doi)
        to_update = models.ArticleMetric.objects.filter(publication=pub).distinct('year')
        entries = {item.year: item for item in to_update}
        citations = {
            int(yr): info
            for yr, info in citations.items()
            if yr.strip()
        }

        for yr, info in citations.items():
            if not yr:
                continue

            year = int(yr)
            if year in entries:
                metric = entries[year]
                metric.citations = info['citations']
                metric.self_cites = info['self_cites']
                metric.modified = now
                update_count += 1
            else:
                to_create.append(models.ArticleMetric(publication=pub, year=year, **info))

        # Update the publication modified date
        models.ArticleMetric.objects.bulk_update(
            entries.values(), fields=['citations', 'self_cites', 'modified']
        )
        time.sleep(1 / 10)

    # Create new metrics entries
    if to_create:
        models.ArticleMetric.objects.bulk_create(to_create, batch_size=100)

    return {'created': len(to_create), 'updated': update_count}


def update_funders():
    publications = models.Publication.objects.filter(
        kind=models.Publication.TYPES.article, funders__isnull=True
    ).in_bulk(
        field_name='code'
    )
    cr = CrossRef()

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
        time.sleep(settings.CROSSREF_THROTTLE)
        count += 1
        print(f'{count / total:0.2%} {count}/{total}')

