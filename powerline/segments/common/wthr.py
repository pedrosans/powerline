# vim:fileencoding=utf-8:noet
from __future__ import (unicode_literals, division, absolute_import, print_function)

import json
import forecastio
import datetime
import math

from powerline.lib.url import urllib_read, urllib_urlencode
from powerline.lib.threaded import KwThreadedSegment
from powerline.segments import with_docstring
from collections import namedtuple


# XXX Warning: module name must not be equal to the segment name as long as this
# segment is imported into powerline.segments.common module.


# Weather condition code descriptions available at
# http://developer.yahoo.com/weather/#codes
weather_conditions_codes = (
	('tornado',                 'stormy'),  # 0
	('tropical_storm',          'stormy'),  # 1
	('hurricane',               'stormy'),  # 2
	('severe_thunderstorms',    'stormy'),  # 3
	('thunderstorms',           'stormy'),  # 4
	('mixed_rain_and_snow',     'rainy' ),  # 5
	('mixed_rain_and_sleet',    'rainy' ),  # 6
	('mixed_snow_and_sleet',    'snowy' ),  # 7
	('freezing_drizzle',        'rainy' ),  # 8
	('drizzle',                 'rainy' ),  # 9
	('freezing_rain',           'rainy' ),  # 10
	('showers',                 'rainy' ),  # 11
	('showers',                 'rainy' ),  # 12
	('snow_flurries',           'snowy' ),  # 13
	('light_snow_showers',      'snowy' ),  # 14
	('blowing_snow',            'snowy' ),  # 15
	('snow',                    'snowy' ),  # 16
	('hail',                    'snowy' ),  # 17
	('sleet',                   'snowy' ),  # 18
	('dust',                    'foggy' ),  # 19
	('fog',                     'foggy' ),  # 20
	('haze',                    'foggy' ),  # 21
	('smoky',                   'foggy' ),  # 22
	('blustery',                'windy' ),  # 23
	('windy',                           ),  # 24
	('cold',                    'day'   ),  # 25
	('clouds',                  'cloudy'),  # 26
	('mostly_cloudy_night',     'cloudy'),  # 27
	('mostly_cloudy_day',       'cloudy'),  # 28
	('partly_cloudy_night',     'cloudy'),  # 29
	('partly_cloudy_day',       'cloudy'),  # 30
	('clear_night',             'night' ),  # 31
	('sun',                     'sunny' ),  # 32
	('fair_night',              'night' ),  # 33
	('fair_day',                'day'   ),  # 34
	('mixed_rain_and_hail',     'rainy' ),  # 35
	('hot',                     'sunny' ),  # 36
	('isolated_thunderstorms',  'stormy'),  # 37
	('scattered_thunderstorms', 'stormy'),  # 38
	('scattered_thunderstorms', 'stormy'),  # 39
	('scattered_showers',       'rainy' ),  # 40
	('heavy_snow',              'snowy' ),  # 41
	('scattered_snow_showers',  'snowy' ),  # 42
	('heavy_snow',              'snowy' ),  # 43
	('partly_cloudy',           'cloudy'),  # 44
	('thundershowers',          'rainy' ),  # 45
	('snow_showers',            'snowy' ),  # 46
	('isolated_thundershowers', 'rainy' ),  # 47
)
# ('day',    (25, 34)),
# ('rainy',  (5, 6, 8, 9, 10, 11, 12, 35, 40, 45, 47)),
# ('cloudy', (26, 27, 28, 29, 30, 44)),
# ('snowy',  (7, 13, 14, 15, 16, 17, 18, 41, 42, 43, 46)),
# ('stormy', (0, 1, 2, 3, 4, 37, 38, 39)),
# ('foggy',  (19, 20, 21, 22, 23)),
# ('sunny',  (32, 36)),
# ('night',  (31, 33))):
weather_conditions_icons = {
	'day':           'DAY',
	'blustery':      'WIND',
	'rainy':         'RAIN',
	'cloudy':        'CLOUDS',
	'snowy':         'SNOW',
	'stormy':        'STORM',
	'foggy':         'FOG',
	'sunny':         'SUN',
	'night':         'NIGHT',
	'windy':         'WINDY',
	'not_available': 'NA',
	'unknown':       'UKN',
}

temp_conversions = {
	'C': lambda temp: temp,
	'F': lambda temp: (temp * 9 / 5) + 32,
	'K': lambda temp: temp + 273.15,
}

# Note: there are also unicode characters for units: ℃, ℉ and  K
temp_units = {
	'C': '°C',
	'F': '°F',
	'K': 'K',
}

_WeatherKey = namedtuple('Key', 'location_query forecast_io')
_ForecastKey = namedtuple('Key', 'api_keys lat lng precipitation_probability')

class WeatherSegment(KwThreadedSegment):
	interval = 600
	default_location = None
	location_urls = {}

	@staticmethod
	def key(location_query=None, forecast_io=None, **kwargs):
		return _WeatherKey(
			location_query,
			_ForecastKey(forecast_io['api_keys'], forecast_io['lat'], forecast_io['lng'], forecast_io['precipitation_probability'])
		)

	def get_request_url(self, location_query):
		try:
			return self.location_urls[location_query]
		except KeyError:
			if location_query is None:
				location_data = json.loads(urllib_read('http://geoip.nekudo.com/api/'))
				location = ','.join((
					location_data['city'],
					location_data['country']['name'],
					location_data['country']['code']
				))
				self.info('Location returned by nekudo is {0}', location)
			else:
				location = location_query
			query_data = {
				'q':
				'use "https://raw.githubusercontent.com/yql/yql-tables/master/weather/weather.bylocation.xml" as we;'
				'select * from weather.forecast where woeid in'
				' (select woeid from geo.places(1) where text="{0}") and u="c"'.format(location).encode('utf-8'),
				'format': 'json',
			}
			self.location_urls[location_query] = url = (
				'http://query.yahooapis.com/v1/public/yql?' + urllib_urlencode(query_data))
			return url

	def compute_state(self, key):
		url = self.get_request_url(key.location_query)
		raw_response = urllib_read(url)
		if not raw_response:
			self.error('Failed to get response')
			return None

		response = json.loads(raw_response)
		try:
			condition = response['query']['results']['channel']['item']['condition']
			condition_code = int(condition['code'])
			temp = float(condition['temp'])
		except (KeyError, ValueError):
			self.exception('Yahoo returned malformed or unexpected response: {0}', repr(raw_response))
			return None

		try:
			icon_names = weather_conditions_codes[condition_code]
		except IndexError:
			if condition_code == 3200:
				icon_names = ('not_available',)
				self.warn('Weather is not available for location {0}', self.location)
			else:
				icon_names = ('unknown',)
				self.error('Unknown condition code: {0}', condition_code)

		if key.forecast_io.api_keys is not None:
			for api_key in key.forecast_io.api_keys.split(","):
				try:
					forecast_data = forecastio.load_forecast(api_key, key.forecast_io.lat, key.forecast_io.lng)
					forecast_data.request_time = datetime.datetime.now()
					break
				except (KeyError, ValueError):
					self.exception('cant access forecastio: {0}', ValueError)

		return (temp, icon_names, forecast_data)

	def render_one(self, weather, icons=None, unit='C', temp_format=None, temp_coldest=-30, temp_hottest=40, forecast_io=None, **kwargs):
		if not weather:
			return None

		temp, icon_names, forecast_data = weather

		for icon_name in icon_names:
			if icons:
				if icon_name in icons:
					icon = icons[icon_name]
					break
		else:
			icon = weather_conditions_icons[icon_names[-1]]

		temp_format = temp_format or ('{temp:.0f}' + temp_units[unit])
		converted_temp = temp_conversions[unit](temp)
		if temp <= temp_coldest:
			gradient_level = 0
		elif temp >= temp_hottest:
			gradient_level = 100
		else:
			gradient_level = (temp - temp_coldest) * 100.0 / (temp_hottest - temp_coldest)
		groups = ['weather_condition_' + icon_name for icon_name in icon_names] + ['weather_conditions', 'weather']
		line = [
			{
				'contents': icon + ' ',
				'highlight_groups': groups,
				'divider_highlight_group': 'background:divider',
			},
			{
				'contents': temp_format.format(temp=converted_temp),
				'highlight_groups': ['weather_temp_gradient', 'weather_temp', 'weather'],
				'divider_highlight_group': 'background:divider',
				'gradient_level': gradient_level,
			},
		]
		if forecast_io is not None:
			line += self.render_forecast(forecast_data, icons['rainy'])
		return line
	def render_forecast(self, forecast_data, icon, **kwargs):
			currently = forecast_data.currently()
			hourly_forecast = forecast_data.hourly()
			worst_change = currently.precipProbability;
			hour_difference = forecast_data.request_time.replace(minute=0, second=0, microsecond=0) - currently.time.replace(minute=0, second=0, microsecond=0)
			rain_forecast = []
			if not WeatherSegment.is_rain_forecast(currently) and worst_change > 0:
				rain_forecast += [
					{
						'contents': ' {0}'.format(icon),
						'highlight_groups': ['weather_condition_rainy', 'weather_conditions', 'weather'],
						'divider_highlight_group': 'background:divider',
					},
					{
						'contents': ' {0}%'.format( math.trunc(worst_change * 100)),
						'highlight_groups': ['weather_temp_gradient', 'weather_temp', 'weather'],
						'divider_highlight_group': 'background:divider',
						'gradient_level': math.trunc(worst_change * 100)
					}
				]
			rain_forecast_counter = 0
			for hour_forecast in hourly_forecast.data[1:]:
				if (math.trunc(hour_forecast.precipProbability * 100) > math.trunc(worst_change * 100)
				    and WeatherSegment.is_rain_forecast(hour_forecast) and rain_forecast_counter <= 6):
					rain_forecast_counter += 1
					worst_change = hour_forecast.precipProbability
					rain_forecast += [
						{
							'contents': ' {0}%'.format( math.trunc(worst_change * 100)),
							'highlight_groups': ['weather_rain_gradient', 'weather_rain', 'weather'],
							'divider_highlight_group': 'background:divider',
							'gradient_level': math.trunc(worst_change * 100)
						},
						{
							'contents': '/{0}'.format( (hour_forecast.time + hour_difference).strftime("%Hh")),
							'divider_highlight_group': 'background:divider',
						}
					]
				if not WeatherSegment.is_rain_forecast(hour_forecast):
					rain_forecast.append(
						{
							'contents': ' ' + hour_forecast.summary + '/' + (hour_forecast.time + hour_difference).strftime("%Hh"),
							'divider_highlight_group': 'background:divider',
						}
					)
					break
			if worst_change > 0:
				return rain_forecast
			return []

	@staticmethod
	def is_rain_forecast(hour_forecast):
		return 'rain' in hour_forecast.summary.lower() or 'drizzle' in hour_forecast.summary.lower()

weather = with_docstring(WeatherSegment(),
'''Return weather from Yahoo! Weather.

Uses GeoIP lookup from http://geoip.nekudo.com to automatically determine
your current location. This should be changed if you’re in a VPN or if your
IP address is registered at another location.

Returns a list of colorized icon and temperature segments depending on
weather conditions.

:param str unit:
	temperature unit, can be one of ``F``, ``C`` or ``K``
:param str location_query:
	location query for your current location, e.g. ``oslo, norway``
:param dict icons:
	dict for overriding default icons, e.g. ``{'heavy_snow' : u'❆'}``
:param str temp_format:
	format string, receives ``temp`` as an argument. Should also hold unit.
:param float temp_coldest:
	coldest temperature. Any temperature below it will have gradient level equal
	to zero.
:param float temp_hottest:
	hottest temperature. Any temperature above it will have gradient level equal
	to 100. Temperatures between ``temp_coldest`` and ``temp_hottest`` receive
	gradient level that indicates relative position in this interval
	(``100 * (cur-coldest) / (hottest-coldest)``).

Divider highlight group used: ``background:divider``.

Highlight groups used: ``weather_conditions`` or ``weather``, ``weather_temp_gradient`` (gradient) or ``weather``.
Also uses ``weather_conditions_{condition}`` for all weather conditions supported by Yahoo.
''')
