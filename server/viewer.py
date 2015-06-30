#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# viewer.py - View aggregated i2p network statistics.
# Author: Chris Barry <chris@barry.im>
# License: This is free and unencumbered software released into the public domain.
#
# NOTE: This file should never write to the database, only read.

import argparse
import datetime
import math
import matplotlib
# We don't want matplotlib to use X11 (https://stackoverflow.com/a/3054314)
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import sqlite3

from jinja2 import Environment, FileSystemLoader

def query_db(conn, query, args=(), one=False):
	cur = conn.execute(query, args)
	rv = cur.fetchall()
	cur.close()
	return (rv[0] if rv else None) if one else rv

# TODO: Make less ugly.
def pie_graph(conn, query, output, title='', lower=0, log=False):
	labels = []
	sizes = []

	res = query_db(conn, query)
	# Sort so the graph doesn't look like complete shit.
	res = sorted(res, key=lambda tup: tup[1])
	for row in res:
		if row[1] > lower:
			labels.append(row[0])
			if log:
				sizes.append(math.log(row[1]))
			else:
				sizes.append(row[1])
	# Normalize.
	norm = [float(i)/sum(sizes) for i in sizes]

	plt.pie(norm,
			labels=labels,
			shadow=True,
			startangle=90,
	)
	plt.axis('equal')
	plt.legend()
	plt.title(title)
	plt.savefig(output)
	plt.clf()

# Plots what is in the 0th column
def plot_x_y(conn, query, output, title='', xlab='', ylab=''):
	fig, ax = plt.subplots()
	res = query_db(conn, query)
	labels = [i[1] for i in res]
	y = [i[0] for i in res]
	x = range(0,len(y))
	plt.title(title)
	plt.xlabel(xlab)
	plt.ylabel(ylab)
	plt.xticks(rotation=10)
	ax.set_xticklabels(labels)
	plt.plot(x, y)
	plt.savefig(output)
	plt.clf()

if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	parser.add_argument('-o', '--output-directory', help='where to save data',type=str, default='./output/')
	args = parser.parse_args()

	# Hides collected data that are too small.
	min_version = 20
	min_country = 20
	interval = 3600 # = 60 minutes

	conn = sqlite3.connect('i2stat.db')

	# Activate pretty graphs.
	#plt.style.use('ggplot')
	plt.xkcd() # If you wanna be fun.

	# Graphs and stuff
	pie_graph(conn,
		query='select country,count(country) from (select country from netdb group by public_key) group by country;',
		output=args.output_directory+'country.png',
		title='Observed Countries',
		lower=min_country,
		log=False)
	pie_graph(conn,
		query='select version,count(version) from (select version from netdb group by public_key) group by version;',
		output=args.output_directory+'version.png',
		title='Observed versions',
		lower=min_version,
		log=False)
	pie_graph(conn,
		query='select sign_key,count(sign_key) from (select sign_key from netdb group by public_key) group by sign_key;',
		output=args.output_directory+'sign_key.png',
		title='Obverved Signing Keys',
		lower=0,
		log=True)
	plot_x_y(conn,
		query='select count(*) as count, time(cast(((submitted)/({0})) as int)*{0}, "unixepoch") as submitted_human from speeds group by cast((submitted)/({0}) as int);'.format(interval),
		output=args.output_directory+'reporting-in.png',
		title='Reporting In',
		xlab='Time',
		ylab='Total')
	plot_x_y(conn, 
		query='select avg(activepeers), time(cast(((submitted)/({0})) as int)*{0}, "unixepoch") as submitted_human from speeds group by cast((submitted)/({0}) as int);'.format(interval),
		output=args.output_directory+'active.png',
		title='Average Active Peers',
		xlab='Time',
		ylab='Peers')
	plot_x_y(conn, 
		query='select avg(highcapacitypeers), time(cast(((submitted)/({0})) as int)*{0}, "unixepoch") as submitted_human from speeds group by cast((submitted)/({0}) as int);'.format(interval),
		output=args.output_directory+'high-cap.png',
		title='High Capacity Peers',
		xlab='Time',
		ylab='Peers')
	plot_x_y(conn,
		query='select avg(tunnelsparticipating), time(cast(((submitted)/({0})) as int)*{0}, "unixepoch") as submitted_human from speeds group by cast((submitted)/({0}) as int);'.format(interval),
		output=args.output_directory+'tunnels-par.png',
		title='Participating Tunnels',
		xlab='Time',
		ylab='Tunnels')

	# Numbers and stuff.
	total = query_db(conn, 'select count(*) from (select public_key,count(public_key) from netdb group by public_key);')
	ipv6_total = query_db(conn, 'select count(*) from (select public_key,count(public_key),ipv6 from netdb group by public_key) where ipv6=1;')
	fw_total = query_db(conn, 'select count(*) from (select public_key,count(public_key),firewalled from netdb group by public_key) where firewalled=1;')
	versions = query_db(conn, 'select version,count(version) as count from (select version from netdb group by public_key) group by version having count > {} order by count desc;'.format(min_version))
	countries = query_db(conn, 'select country,count(country) as count from (select country from netdb where firewalled=0 group by public_key) group by country having count >= {} order by count(country) desc;'.format(min_country))
	sign_keys = query_db(conn, 'select sign_key,count(sign_key) as count from (select sign_key from netdb group by public_key) group by sign_key order by count(sign_key) desc;')
	sightings = query_db(conn, 'select version, datetime(min(submitted), "unixepoch") from netdb group by version order by submitted;')

	# The selects should be averages per period. This is a bit messy but should be right.
	speeds = query_db(conn, 'select submitter,avg(activepeers),avg(highcapacitypeers),avg(tunnelsparticipating), datetime(cast(((submitted)/({0})) as int)*{0}, "unixepoch") as submitted_human, \
	count(*) as count from speeds group by cast((submitted)/({0}) as int);'.format(interval))

	env = Environment(loader=FileSystemLoader('templates'))
	template = env.get_template('index.html')
	output = template.render(
		total=total[0][0],
		ipv6_total=ipv6_total[0][0],
		fw_total=fw_total[0][0],
		sightings=sightings,
		versions=versions,
		countries=countries,
		sign_keys=sign_keys,
		speeds=speeds,
		time=str(datetime.datetime.utcnow())[:-3]
	)
	with open(args.output_directory+'index.html', 'wb') as f:
		f.write(output)

