# vim:fileencoding=utf-8:noet
from __future__ import (unicode_literals, division, absolute_import, print_function)

import forecastio
import datetime
import math

from powerline.lib.threaded import KwThreadedSegment
from powerline.segments import with_docstring
from collections import namedtuple

_ForecastKey = namedtuple('Key', 'api_keys lat lng')


class WeatherSegment(KwThreadedSegment):

	interval = 600
	default_location = None
	location_urls = {}
	evaluations_cache = {}

	@staticmethod
	def key(location_query=None, forecast_io=None, **kwargs):
		return _ForecastKey(forecast_io['api_keys'], forecast_io['lat'], forecast_io['lng'])

	def compute_state(self, key):
		forecast_data = None
		for api_key in key.api_keys.split(","):
			try:
				forecast_data = forecastio.load_forecast(api_key, key.lat, key.lng, None, 'ca')
				forecast_data.request_time = datetime.datetime.now()
				forecast_data.currently_data = forecast_data.currently()
				hour_difference = forecast_data.request_time.replace(minute=0, second=0, microsecond=0) - forecast_data.currently_data.time.replace(minute=0, second=0, microsecond=0)
				forecast_data.currently_data.time = forecast_data.currently_data.time + hour_difference
				forecast_data.hourly_data = forecast_data.hourly().data
				for hour_forecast in forecast_data.hourly_data:
					hour_forecast.time = hour_forecast.time + hour_difference
				evaluations_cache = {}
				break
			except (KeyError, ValueError):
				self.exception('cant access forecastio: {0}', ValueError)

		return (None, None, forecast_data)

	def render_one(self, weather, icons=None, unit='C', temp_format=None, temp_coldest=-30, temp_hottest=40, forecast_io=None, **kwargs):
		if not weather:
			return None

		temp, icon_names, forecast_data = weather

		return self.render_forecast(forecast_data, icons)

	def render_forecast(self, forecast_data, icons, **kwargs):
			worst_prediction = forecast_data.currently_data.precipProbability;
			rain_forecast = []
			icon_shown = False
			rain_forecast_counter = 0
			if WeatherSegment.is_rain_forecast(forecast_data.currently_data):
				icon_shown = True
			elif worst_prediction > 0:
				rain_forecast += WeatherSegment.assemble_rain_forecast(forecast_data.currently_data, icons['rain'], None)
				icon_shown = True
			for hour_forecast in forecast_data.hourly_data[1:24]:
				if (math.trunc(hour_forecast.precipProbability * 100) > math.trunc(worst_prediction * 100) and WeatherSegment.is_rain_forecast(hour_forecast) and rain_forecast_counter < 3):
					rain_forecast_counter += 1
					worst_prediction = hour_forecast.precipProbability
					rain_forecast += WeatherSegment.assemble_rain_forecast(hour_forecast, (None if icon_shown else icons[hour_forecast.icon]), hour_forecast.time)
					icon_shown = True
				if rain_forecast_counter > 0 and not WeatherSegment.is_rain_forecast(hour_forecast):
					icon = None
					if hour_forecast.icon in icons:
						icon = icons[hour_forecast.icon]
					rain_forecast += WeatherSegment.assemble_rain_forecast(hour_forecast, icon, hour_forecast.time)
					break
			return rain_forecast

	@staticmethod
	def is_rain_forecast(hour_forecast):
		return 'rain' in hour_forecast.summary.lower() or 'drizzle' in hour_forecast.summary.lower()

	@staticmethod
	def assemble_rain_forecast(data, rainy_icon, hour):
		hour_forecast = []
		if rainy_icon is not None:
			hour_forecast.append(
				{
					'contents': '{0} '.format(rainy_icon),
					'divider_highlight_group': 'background:divider',
				}
			)
		elif hour:
			hour_forecast.append({'contents': ' ' })
		hour_forecast.append(
			{
				'contents': '{0}%'.format( math.trunc(data.precipProbability * 100)),
				'highlight_groups': ['weather_rain_gradient', 'weather_rain', 'weather'],
				'divider_highlight_group': 'background:divider',
				'gradient_level': math.trunc(data.precipProbability * 100)
			}
		)
		if hour:
			hour_forecast.append(
				{
					'contents': '/{0}'.format( hour.strftime("%Hh")),
					'divider_highlight_group': 'background:divider',
				}
			)
		return hour_forecast


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
