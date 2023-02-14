"""Sample implementations for IntegrationPlugin."""

import json

from common.models import WebConnectionData
from django.contrib.sites.models import Site
from django.http import Http404
from django.shortcuts import redirect
from django.urls import re_path
from django.utils.http import urlquote_plus
from django.utils.translation import gettext_lazy as _
from InvenTree.permissions import auth_exempt
from InvenTree.tasks import offload_task
from plugin import InvenTreePlugin
from plugin.base.supplier.mixins import SearchRunResult  # SearchResult
from plugin.mixins import (APICallMixin, AppMixin, SettingsMixin,
                           SupplierMixin, UrlsMixin)
from part.models import PartCategory


class DigikeyPlugin(APICallMixin, AppMixin, SupplierMixin, SettingsMixin, UrlsMixin, InvenTreePlugin):
    """Plugin to integrate Digikey APIs into InvenTree."""

    NAME = "Digikey Supplier Integration"
    SLUG = "digikey"
    TITLE = "Digikey integration"

    DIGI_AUTH_URL = 'https://api.digikey.com/v1/oauth2/authorize'
    DIGI_AUTH_TOKEN = 'https://api.digikey.com/v1/oauth2/token'
    DIGI_URL_BASE = 'https://api.digikey.com'

    SETTINGS = {
        'SEARCH_ENABLED': {
            'name': _('Enable Search'),
            'description': _('Enable integration into search'),
            'default': True,
            'validator': bool,
        },
        'ORDER_ENABLED': {
            'name': _('Enable Order'),
            'description': _('Enable integration into digikeys order system'),
            'default': True,
            'validator': bool,
        },
        'RELATED_VENDOR': {
            'name': 'Company',
            'description': 'Select the company that is used to represent digikey.',
            'model': 'company.company',
        },
    }

    CONNECTIONS = {
        'digikey_account': WebConnectionData(
            name='DigiKey Account',
            description=_('Account that should be used to access the digikey API'),
            settings={
                'DIGI_CLIENT_ID': {
                    'name': _('API Key'),
                    'description': _('Key required for accessing external API'),
                },
                'DIGI_CLIENT_SECRET': {
                    'name': _('API Secret'),
                    'description': _('Key required for accessing external API'),
                },
                'LOCALE_SITE': {
                    'name': _("Locale-Site"),
                    'description': _('A setting with multiple choices'),
                    'choices': [
                        ('US', 'US'), ('CA', 'CA'), ('JP', 'JP'), ('UK', 'UK'), ('DE', 'DE'), ('AT', 'AT'), ('BE', 'BE'), ('DK', 'DK'), ('FI', 'FI'), ('GR', 'GR'), ('IE', 'IE'), ('IT', 'IT'), ('LU', 'LU'), ('NL', 'NL'), ('NO', 'NO'), ('PT', 'PT'), ('ES', 'ES'), ('KR', 'KR'), ('HK', 'HK'), ('SG', 'SG'), ('CN', 'CN'), ('TW', 'TW'), ('AU', 'AU'), ('FR', 'FR'), ('IN', 'IN'), ('NZ', 'NZ'), ('SE', 'SE'), ('MX', 'MX'), ('CH', 'CH'), ('IL', 'IL'), ('PL', 'PL'), ('SK', 'SK'), ('SI', 'SI'), ('LV', 'LV'), ('LT', 'LT'), ('EE', 'EE'), ('CZ', 'CZ'), ('HU', 'HU'), ('BG', 'BG'), ('MY', 'MY'), ('ZA', 'ZA'), ('RO', 'RO'), ('TH', 'TH'), ('PH', 'PH'),
                    ],
                    'default': 'US',
                },
                'LOCALE_LANGUAGE': {
                    'name': _("Locale-Language"),
                    'description': _('A setting with multiple choices'),
                    'choices': [
                        ('br', 'br'), ('cs', 'cs'), ('da', 'da'), ('de', 'de'), ('en', 'en'), ('es', 'es'), ('fi', 'fi'), ('fr', 'fr'), ('he', 'he'), ('hu', 'hu'), ('it', 'it'), ('ja', 'ja'), ('ko', 'ko'), ('nl', 'nl'), ('no', 'no'), ('pl', 'pl'), ('pt', 'pt'), ('ro', 'ro'), ('sv', 'sv'), ('th', 'th'), ('zhs', 'zhs'), ('zht', 'zht'),
                    ],
                    'default': 'en',
                },
                'LOCALE_CURRENCY': {
                    'name': _("Locale-Currency"),
                    'description': _('A setting with multiple choices'),
                    'choices': [
                        ('USD', 'USD'), ('CAD', 'CAD'), ('JPY', 'JPY'), ('GBP', 'GBP'), ('EUR', 'EUR'), ('HKD', 'HKD'), ('SGD', 'SGD'), ('TWD', 'TWD'), ('KRW', 'KRW'), ('AUD', 'AUD'), ('NZD', 'NZD'), ('INR', 'INR'), ('DKK', 'DKK'), ('NOK', 'NOK'), ('SEK', 'SEK'), ('ILS', 'ILS'), ('CNY', 'CNY'), ('PLN', 'PLN'), ('CHF', 'CHF'), ('CZK', 'CZK'), ('HUF', 'HUF'), ('RON', 'RON'), ('ZAR', 'ZAR'), ('MYR', 'MYR'), ('THB', 'THB'), ('PHP', 'PHP'),
                    ],
                    'default': 'USD',
                },
                'CUSTOMER_ID': {
                    'name': _('Customer-Id'),
                    'description': _('Key required for accessing external API'),
                },
                'RESPONSE': {
                    'name': _('Response'),
                    'description': _('Key required for accessing external API'),
                },
                'AUTHENTICATED': {
                    'name': _('Authenticated'),
                    'description': _('Is the connection authenticated?'),
                    'default': False,
                    'validator': bool,
                },
            }
        ),
    }
    STD_CONNECTION = 'digikey_account'

    # oauth functions
    def get_redirect_url(self):
        """Returns OAuth redirection urls."""
        site_url = Site.objects.all().order_by('id').first()
        return f'{site_url.domain}/{self.base_url}digikey_callback/'

    def get_token(self, code):
        """Fetch token from digikey and save it to connection."""
        response = self.api_call(
            self.DIGI_AUTH_TOKEN, method='POST',
            data={
                'code': code,
                'client_id': self.get_con('DIGI_CLIENT_ID'),
                'client_secret': self.get_con('DIGI_CLIENT_SECRET'),
                'redirect_uri': self.get_redirect_url(),
                'grant_type': 'authorization_code',
            },
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            endpoint_is_url=True
        )

        if response.get('access_token'):
            # save reference
            self.set_con('AUTHENTICATED', True)
            self.set_con('RESPONSE', json.dumps(response))
        else:
            # log error
            # TODO log error
            pass

    # views
    @auth_exempt
    def view_callback(self, request):
        """Callback for oauth setup."""
        code = request.GET.get('code')
        if code:
            offload_task(self.get_token, code)
            return redirect(self.settings_url)
        raise Http404('No code found')

    def view_setup(self, request):
        """Start setup for digikey credentials."""
        client_id = self.get_con('DIGI_CLIENT_ID')
        auth_url = self.DIGI_AUTH_URL
        return redirect(f'{auth_url}?response_type=code&client_id={client_id}&redirect_uri={urlquote_plus(self.get_redirect_url())}')

    def setup_urls(self):
        """Urls that are exposed by this plugin."""
        return [
            re_path(r'^digikey_callback/', self.view_callback, name='callback'),
            re_path(r'^setup/', self.view_setup, name='setup'),
        ]

    # ui interaction
    def raise_auth_error(self, msg):
        """Raise an authentication error to the user."""
        raise PermissionError(f'Authentication error occured!\n{msg}')

    def digikey_search_settings(self, records: int = 10):
        """Returns search settings for digikey api."""
        return {
            "RecordCount": records,
            "RecordStartPosition": 0,
            "Filters": {
                "TaxonomyIds": [0],
                "ManufacturerIds": [0],
            },
            "Sort": {
                "SortOption": "SortByDigiKeyPartNumber",
                "Direction": "Ascending",
                "SortParameterId": 0
            },
            "RequestedQuantity": 0,
            "SearchOptions": ["ManufacturerPartSearch"],
            "ExcludeMarketPlaceProducts": True
        }

    def digikey_headers(self):
        """Returns default part headers for digikey."""
        code = json.loads(self.get_con('RESPONSE', default={})).get('access_token')
        return {
            'Authorization': f'Bearer {code}',
            'X-DIGIKEY-Client-Id': self.get_con('DIGI_CLIENT_ID'),
            'X-DIGIKEY-Locale-Site': self.get_con('LOCALE_SITE'),
            'X-DIGIKEY-Locale-Language': self.get_con('LOCALE_LANGUAGE'),
            'X-DIGIKEY-Locale-Currency': self.get_con('LOCALE_CURRENCY'),
            'X-DIGIKEY-Customer-Id': self.get_con('CUSTOMER_ID'),
            'Content-Type': 'application/json'
        }

    def check_auth(self):
        # Check if we are authenticated - pass if not
        if not self.get_con('AUTHENTICATED'):
            self.raise_auth_error('Connection not authenticated')
            return None

    def digikey_api_keyword(self, term):
        """Fetches search results form the keyword API."""
        self.check_auth()

        # Get data
        data = self.digikey_search_settings()
        data.update({"Keywords": term})
        response = self.api_call(
            f'{self.DIGI_URL_BASE}/Search/v3/Products/Keyword?includes={term}',
            method='POST',
            json=data,
            headers=self.digikey_headers(),
            endpoint_is_url=True, simple_response=False
        )

        # Check response
        if response.status_code != 200:
            if response.status_code == 401 and response.json().get('ErrorMessage') == 'Bearer token  expired':
                self.raise_auth_error('Token has expired')
                return None
            raise ValueError(_('An error occured while fetching the data.'), response.content)

        # TODO parse results
        results = response.json()

        return results

    def digikey_api_part_detail(self, term, category):
        """Fetches part from the PartDetail API."""
        self.check_auth()

        # Get data
        data = self.digikey_search_settings()
        data.update({"Keywords": term})
        response = self.api_call(
            f'{self.DIGI_URL_BASE}/Search/v3/Products/Keyword?includes={term}',
            method='POST',
            json=data,
            headers=self.digikey_headers(),
            endpoint_is_url=True, simple_response=False
        )

        # Check response
        if response.status_code != 200:
            if response.status_code == 401 and response.json().get('ErrorMessage') == 'Bearer token  expired':
                self.raise_auth_error('Token has expired')
                return None
            raise ValueError(_('An error occured while fetching the data.'), response.content)

        # TODO parse results
        results = response.json()

        return results

    # -------------------------------------- #
    # mixin: supplier
    # -------------------------------------- #
    def search_action(self, term: str, exact: bool = False, safe_results: bool = True) -> SearchRunResult:
        """Runs search again supplier API."""
        results = self.digikey_api_keyword(term)
        return SearchRunResult(term=term, exact=exact, safe_results=safe_results, results=results)

    def import_part(self, term: str, category: PartCategory) -> bool:
        """Tries to import a part by term.

        Returns bool if import was successfull.
        """
        result = self.digikey_api_part_detail(term=term, category=category)
        return bool(result)
