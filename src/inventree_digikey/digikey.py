"""Sample implementations for IntegrationPlugin."""

import json

from common.models import WebConnectionData
from django.contrib.sites.models import Site
from django.http import Http404
from django.shortcuts import redirect
from django.urls import re_path
from django.utils.http import urlquote_plus
from django.utils.translation import gettext_lazy as _
from InvenTree.permissions import login_exempt
from InvenTree.tasks import offload_task
from plugin import InvenTreePlugin
from plugin.base.supplier.mixins import SearchRunResult  # SearchResult
from plugin.mixins import (APICallMixin, AppMixin, SettingsMixin,
                           SupplierMixin, UrlsMixin)


class DigikeyPlugin(APICallMixin, AppMixin, SupplierMixin, SettingsMixin, UrlsMixin, InvenTreePlugin):
    """Plugin to integrate Digikey APIs into InvenTree."""

    NAME = "Digikey Supplier Integration"
    SLUG = "digikey"
    TITLE = "Digikey integration"

    DIGI_AUTH_URL = 'https://sandbox-api.digikey.com/v1/oauth2/authorize'
    DIGI_AUTH_TOKEN = 'https://sandbox-api.digikey.com/v1/oauth2/token'
    DIGI_URL_BASE = 'https://sandbox-api.digikey.com'

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

    # Connection details
    # TODO move out
    def get_con(self, key: str, ref: str = None, default=None):
        """Get webconnection setting data."""
        def ret_default(val):
            if not val and default:
                return default
            return val

        ref = ref if ref else self.STD_CONNECTION
        qs = self.db.webconnections.filter(connection_key=ref)
        ret = [a.settings.get(key=key).value for a in qs]
        if len(ret) == 1:
            return ret_default(ret[0])
        return ret_default(ret)

    def set_con(self, key: str, val, ref: str = None):
        """Set webconnection setting data."""
        ref = ref if ref else self.STD_CONNECTION
        qs = self.db.webconnections.filter(connection_key=ref)
        if len(qs) > 1:
            raise NotImplementedError('This function is not implemented!')
        setting = qs[0].settings.get(key=key)
        setting.value = val
        setting.save()

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
            endpoint_is_url=True, json_data=False
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
    @login_exempt
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
    def raise_aut_error(self, msg):
        """Raise an authentication error to the user."""
        # TODO send notification
        pass

    def digikey_search_settings(self, keyword, records: int = 10):
        """Returns search settings for digikey api."""
        return {
            "Keywords": keyword,
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

    def digikey_api_keyword(self, term):
        """Fetches search results form the keyword API."""
        # Check if we are authenticated - pass if not
        if not self.get_con('AUTHENTICATED'):
            self.raise_aut_error()
            return None

        # Get data
        response = self.api_call(
            f'{self.DIGI_URL_BASE}/Search/v3/Products/Keyword?includes={term}',
            method='POST',
            data=self.digikey_search_settings(term),
            headers=self.digikey_headers(),
            endpoint_is_url=True,
        )

        # Check response
        if 'ErrorMessage' in response:
            if response.get('StatusCode') == 401 and response.get('ErrorMessage') == 'Bearer token  expired':
                self.raise_aut_error()
                return None
            raise ValueError(_('An error occured while fetching the data.'), response)

        # TODO parse results
        results = response

        return results

    def search_action(self, term: str, exact: bool = False, safe_results: bool = True) -> SearchRunResult:
        """Runs search again supplier API."""
        def retrun_result(data):
            return SearchRunResult(term=term, exact=exact, safe_results=safe_results, results=data)

        results = self.digikey_api_keyword(term)

        return retrun_result(results)
