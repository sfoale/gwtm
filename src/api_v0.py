# -*- coding: utf-8 -*-

from flask import request
from sqlalchemy import func, or_
import json, datetime
import boto3
import io

from src import app
from src.gwtmconfig import config
from . import function
from . import models
from . import enums
from . import gwtm_io

db = models.db

def initial_request_parse(request, only_json=False):

	args = None
	try:
		args = request.get_json()
	except:
		if only_json:
			return False, "Endpoint only accepts json argument parameters", args, None
		pass

	if args is None:
		args = request.args

	if args is None:
		return False, "Invalid Arguments.", args, None

	if "api_token" in args:
		apitoken = args['api_token']
		if apitoken is not None:
			user = db.session.query(models.users).filter(models.users.api_token ==  apitoken).first()
			if user is None:
				return False, "Invalid api_token", args, None
		else:
			return False, "Invalid api_token", args, None
	else:
		return False, "api_token is required", args, None

	models.useractions.write_action(request=request, current_user=user)

	return True, '', args, user


def make_response(response_message, status_code):
	response = app.response_class(response=response_message,
                                  status=status_code,
                                  mimetype='application/json')
	return response


#API Endpoints

#Get instrument footprints
@app.route("/api/v0/footprints", methods=['GET'])
def get_footprints():

	valid, message, args, user = initial_request_parse(request=request)

	if not valid:
		return make_response(message, 500)

	filter = []
	if "id" in args:
		if function.isInt(args['id']):
			inst_id = int(args['id'])
			filter.append(models.footprint_ccd.instrumentid == inst_id)
	if "name" in args:
		filter.append(models.footprint_ccd.instrumentid == models.instrument.id)
		name = args.get('name')
		ors = []
		ors.append(models.instrument.instrument_name.contains(name.strip()))
		ors.append(models.instrument.nickname.contains(name.strip()))
		filter.append(or_(*ors))

	footprints= db.session.query(models.footprint_ccd).filter(*filter).all()
	footprints = [x.json for x in footprints]

	return make_response(json.dumps(footprints), 200)


@app.route('/api/v0/remove_event_galaxies', methods=['POST'])
def remove_event_galaxies():

	valid, message, args, user = initial_request_parse(request=request)

	if not valid:
		return make_response(message, 500)

	if "listid" in args:
		listid = args['listid']
		if function.isInt(listid):
			gallist = db.session.query(models.gw_galaxy_list).filter(models.gw_galaxy_list.id==listid).first()
			if gallist is not None:
				if user.id == gallist.submitterid:
					gallist_entries = db.session.query(models.gw_galaxy_entry).filter(models.gw_galaxy_entry.listid == listid)
					db.session.delete(gallist)
					for ge in gallist_entries:
						db.session.delete(ge)
					db.session.commit()
					return make_response("Successfully deleted your galaxy list"), 200 
				else:
					return make_response('You can only delete information related to your api_token! shame shame', 500)
			else:
				return make_response('No galaxies with that listid'), 500 
		else:
			return make_response('Invalid listid', 500)
	else:
		return make_response('Event galaxy listid is required', 500)


@app.route('/api/v0/event_galaxies', methods=['GET'])
def get_event_galaxies():

	valid, message, args, user = initial_request_parse(request=request)

	if not valid:
		return make_response(message, 500)

	filter = [models.gw_galaxy_entry.listid == models.gw_galaxy_list.id]

	if 'graceid' in args:
		graceid = models.gw_alert.graceidfromalternate(args['graceid'])
		filter.append(models.gw_galaxy_list.graceid == graceid)
	else:
		return make_response("\'graceid\' is required", 500)

	if "timesent_stamp" in args:
		timesent_stamp = args['timesent_stamp']
		try:
			time = datetime.datetime.strptime(timesent_stamp, "%Y-%m-%dT%H:%M:%S.%f")
		except:
			return make_response("Error parsing date. Should be %Y-%m-%dT%H:%M:%S.%f format. e.g. 2019-05-01T12:00:00.00", 500)

		alert = db.session.query(models.gw_alert).filter(
			models.gw_alert.timesent < time + datetime.timedelta(seconds=15),
			models.gw_alert.timesent > time - datetime.timedelta(seconds=15),
			models.gw_alert.graceid == graceid).first()
		if alert is None:
			return make_response('Invalid \'timesent_stamp\' for event\n Please visit http://treasuremap.space/alerts?graceids={} for valid timesent stamps for this event'.format(graceid), 500)
		else:
			filter.append(models.gw_galaxy_list.alertid == alert.id)

	if 'listid' in args:
		if function.isInt(args['listid']):
			filter.append(models.gw_galaxy_list.id == int(args['listid']))
		else:
			return make_response('Invalid \'listid\'', 500)

	if 'groupname' in args:
		filter.append(models.gw_galaxy_list.groupname == args['groupname'])

	if 'score_gt' in args:
		if function.isFloat(args['score_gt']):
			sgt = float(args['score_gt'])
			filter.append(models.gw_galaxy_entry.score >= sgt)
	if 'score_lt' in args:
		if function.isFloat(args['score_lt']):
			slt = float(args['score_lt'])
			filter.append(models.gw_galaxy_entry.score <= slt)

	gal_entries = db.session.query(models.gw_galaxy_entry).filter(*filter).all()
	gal_entries = [x.json for x in gal_entries]

	return make_response(json.dumps(gal_entries), 200)


@app.route('/api/v0/event_galaxies', methods=['POST'])
def post_event_galaxies():

	try:
		args = request.get_json()
	except:
		return("Whoaaaa that JSON is a little wonky")

	post_doi = False
	warnings = []
	errors = []

	if "api_token" in args:
		apitoken = args['api_token']
		user = db.session.query(models.users).filter(models.users.api_token ==  apitoken).first()
		if user is None:
			return make_response("invalid api_token", 500)
	else:
		return make_response("api_token is required", 500)

	models.useractions.write_action(request=request, current_user=user)

	if "graceid" in args:
		graceid = args['graceid']
		graceid = models.gw_alert.graceidfromalternate(graceid)
	else:
		return make_response('graceid is required', 500)

	if "timesent_stamp" in args:
		timesent_stamp = args['timesent_stamp']
		try:
			time = datetime.datetime.strptime(timesent_stamp, "%Y-%m-%dT%H:%M:%S.%f")
		except:
			return make_response("Error parsing date. Should be %Y-%m-%dT%H:%M:%S.%f format. e.g. 2019-05-01T12:00:00.00", 500)

		alert = db.session.query(models.gw_alert).filter(
			models.gw_alert.timesent < time + datetime.timedelta(seconds=15),
			models.gw_alert.timesent > time - datetime.timedelta(seconds=15),
			models.gw_alert.graceid == args['graceid'],
			~models.gw_alert.alert_type.contains("ExtCoinc")
		).order_by(models.gw_alert.datecreated.desc()).first()
		if alert is None:
			return make_response('Invalid \'timesent_stamp\' for event\n Please visit http://treasuremap.space/alerts?graceids={} for valid timesent stamps for this event'.format(graceid), 500)
	else:
		return make_response('timesent_stamp is required', 500)

	if "groupname" in args:
		groupname = args['groupname']
	else:
		groupname = user.username
		warnings.append("no groupname given. Defaulting to api_token username")

	reference = None
	if "reference" in args:
		reference = args['reference']

	if 'request_doi' in args:
		post_doi = bool(args['request_doi'])
		if 'creators' in args:
			creators = args['creators']
			for c in creators:
				if 'name' not in c.keys() or 'affiliation' not in c.keys():
					return make_response('name and affiliation are required for DOI creators json list', 500)
		elif 'doi_group_id' in args:
				valid, creators = models.doi_author.construct_creators(args['doi_group_id'], user.id)
				if not valid:
					return make_response("Invalid doi_group_id. Make sure you are the User associated with the DOI group", 500)
		else:
			creators = [{ 'name':str(user.firstname) + ' ' + str(user.lastname) }]

	#maybe include the possibility for a different delimiter for alert types as well. Not only graceids
	gw_galist = models.gw_galaxy_list(
		submitterid = user.id,
		graceid = graceid,
		alertid = alert.id,
		groupname = groupname,
		reference = reference,
	)
	db.session.add(gw_galist)
	db.session.flush()

	valid_galaxies = []

	if "galaxies" in args:
		galaxies = args['galaxies']
		for g in galaxies:
			gw_galentry = models.gw_galaxy_entry()
			v = gw_galentry.from_json(g)
			if v.valid:
				gw_galentry.listid = gw_galist.id
				db.session.add(gw_galentry)
				valid_galaxies.append(gw_galentry)
				if len(v.warnings) > 0:
					warnings.append(["Object: " + json.dumps(g), v.warnings])

			else:
				errors.append(["Object: "+json.dumps(g), v.errors])

	else:
		return make_response("a list of galaxies is required", 500)

	doi_string = '. '

	db.session.flush()
	db.session.commit()

	if post_doi:
		doi_id, url = function.create_galaxy_score_doi(valid_galaxies, creators, reference, graceid, alert.alert_type)
		if url is None and doi_id is not None:
			errors.append('There was an error with the DOI request. Please ensure that author group\'s ORIC/GND values are accurate')
		else:
			gw_galist.doi_id = doi_id
			gw_galist.doi_url = url
			doi_string = ". DOI url: {}.".format(url)

			db.session.flush()
			db.session.commit()

	return make_response(json.dumps({"Successful adding of "+str(len(valid_galaxies))+" galaxies for event "+graceid+doi_string+" List ID" :str(gw_galist.id),
					"ERRORS":errors,
					"WARNINGS":warnings}), 200)


@app.route("/api/v0/glade", methods=['GET'])
def get_galaxies():

	valid, message, args, user = initial_request_parse(request=request)

	if not valid:
		return make_response(message, 500)

	filter = []
	filter1 = []
	filter1.append(models.glade_2p3.pgc_number != -1)
	filter1.append(models.glade_2p3.distance > 0)
	filter1.append(models.glade_2p3.distance < 100)
	trim = db.session.query(models.glade_2p3).filter(*filter1)

	orderby = []
	if 'ra' in args and 'dec' in args:
		ra = args.get('ra')
		dec = args.get('dec')
		if function.isFloat(ra) and function.isFloat(dec):
			geom = "SRID=4326;POINT("+str(ra)+" "+str(dec)+")"
			orderby.append(func.ST_Distance(models.glade_2p3.position, geom))
	if 'name' in args:
		name = args.get('name')
		ors = []
		ors.append(models.glade_2p3._2mass_name.contains(name.strip()))
		ors.append(models.glade_2p3.gwgc_name.contains(name.strip()))
		ors.append(models.glade_2p3.hyperleda_name.contains(name.strip()))
		ors.append(models.glade_2p3.sdssdr12_name.contains(name.strip()))
		filter.append(or_(*ors))

	galaxies = trim.filter(*filter).order_by(*orderby).limit(15).all()

	galaxies = [x.json for x in galaxies]

	return make_response(json.dumps(galaxies), 200)


#Post Pointing/s
#Parameters: List of Pointing JSON objects
#Returns: List of assigned IDs
#Comments: Check if instrument configuration already exists to avoid duplication.
#Check if pointing is centered at a galaxy in one of the catalogs and if so, associate it.
@app.route("/api/v0/pointings", methods=["POST"])
def add_pointings():

	valid, message, args, user = initial_request_parse(request=request, only_json=True)

	if not valid:
		return make_response(message, 500)

	valid_gid = False
	post_doi = False

	points = []
	errors = []
	warnings = []

	if "graceid" in args:
		gid = args['graceid']
		gid = models.gw_alert.graceidfromalternate(gid)
		current_gids = db.session.query(models.gw_alert.graceid).filter(models.gw_alert.graceid == gid).all()
		if len(current_gids) > 0:
			valid_gid = True
		else:
			return make_response("Invalid graceid", 500)
	else:
		return make_response("graceid is required", 500)

	if 'request_doi' in args:
		post_doi = bool(args['request_doi'])
		if 'creators' in args:
			creators = args['creators']
			for c in creators:
				if 'name' not in c.keys() or 'affiliation' not in c.keys():
					return make_response('name and affiliation are required for DOI creators json list', 500)
		elif 'doi_group_id' in args:
				valid, creators = models.doi_author.construct_creators(args['doi_group_id'], user.id)
				if not valid:
					return make_response("Invalid doi_group_id. Make sure you are the User associated with the DOI group", 500)
		else:
			creators = [{ 'name':str(user.firstname) + ' ' + str(user.lastname) }]

	dbinsts = db.session.query(models.instrument.instrument_name,
							   models.instrument.id).all()

	filter = [models.pointing.submitterid == user.id]

	otherpointings = db.session.query(models.pointing).filter(
		models.pointing.id == models.pointing_event.pointingid,
		models.pointing_event.graceid == gid
	).all()

	if "pointing" in args:
		p = args['pointing']
		mp = models.pointing()
		if 'id' in p:
			if function.isInt(p['id']):
				planned_pointings = models.pointing.pointings_from_IDS([p['id']], filter)
		v = mp.from_json(p, dbinsts, user.id, planned_pointings, otherpointings)
		if v.valid:
			points.append(mp)
			if len(v.warnings) > 0:
				warnings.append(["Object: " + json.dumps(p), v.warnings])
			db.session.add(mp)
		else:
			errors.append(["Object: "+json.dumps(p), v.errors])

	elif "pointings" in args:
		pointings = args['pointings']
		planned_ids = []
		for p in pointings:
			if 'id' in p:
				if function.isInt(p['id']):
					planned_ids.append(int(p['id']))
		planned_pointings = models.pointing.pointings_from_IDS(planned_ids, filter)

		for p in pointings:
			mp = models.pointing()
			v = mp.from_json(p, dbinsts, user.id, planned_pointings, otherpointings)
			if v.valid:
				points.append(mp)
				db.session.add(mp)
				if len(v.warnings) > 0:
					warnings.append(["Object: " + json.dumps(p), v.warnings])
			else:
				errors.append(["Object: "+json.dumps(p), v.errors])
	else:
		return make_response("Invalid request: json pointing or json list of pointings are required\nYou can find API documentation here: treasuremap.space/documentation.com", 500)

	db.session.flush()

	if valid_gid:
		for p in points:
			pe = models.pointing_event(
				pointingid = p.id,
				graceid = gid)
			db.session.add(pe)

	db.session.flush()
	db.session.commit()

	if post_doi and len(points):
		insts = db.session.query(models.instrument).filter(models.instrument.id.in_([x.instrumentid for x in points]))
		inst_set = list(set([x.instrument_name for x in insts]))

		if 'doi_url' in args:
			doi_id, doi_url = 0, args['doi_url']
		else:
			gid = models.gw_alert.alternatefromgraceid(gid)
			doi_id, doi_url = function.create_pointing_doi(points, gid, creators, inst_set)

		if doi_id is not None:
			for p in points:
				p.doi_url = doi_url
				p.doi_id = doi_id

			db.session.flush()
			db.session.commit()

			response_message = json.dumps({"pointing_ids":[x.id for x in points], "ERRORS":errors, "WARNINGS":warnings, "DOI":doi_url})
			return make_response(response_message, 200)

	response_message = json.dumps({"pointing_ids":[x.id for x in points], "ERRORS":errors, "WARNINGS":warnings})
	return make_response(response_message, 200)


#Get Pointing/s
#Parameters: List of ID/s, type/s, group/s, user/s, and/or time/s constraints (to be AND’ed).
#Returns: List of PlannedPointing JSON objects
@app.route("/api/v0/pointings", methods=["GET"])
def get_pointings():

	valid, message, args, user = initial_request_parse(request=request)

	if not valid:
		return app.response_class(response=message,
                                  status=500,
                                  mimetype='application/json')

	filter=[]

	if "graceid" in args:
		graceid = args.get('graceid')
		graceid = models.gw_alert.graceidfromalternate(graceid)
		filter.append(models.pointing_event.graceid == graceid)
		filter.append(models.pointing_event.pointingid == models.pointing.id)

	if 'graceids' in args:
		argname = "graceids"
		arg = args.get(argname)
		if isinstance(arg, str):
			try:
				arg = str(arg).split('[')[1].split(']')[0].split(',')
			except:
				return make_response(f'Error parsing \'{argname}\'. required format is a list: \'[graceid1, graceid2...]\'', 500)
		if isinstance(arg, list):
			gids = []
			for g in arg:
				gids.append(models.gw_alert.graceidfromalternate(g))
			filter.append(models.pointing_event.graceid.in_(gids))
			filter.append(models.pointing_event.pointingid == models.pointing.id)
		else:
			return make_response(f'Error parsing \'{argname}\'. required format is a list: \'[graceid1, graceid2...]\'', 500)

	if "id" in args:
		_id = args.get('id')
		if str(_id).isdigit():
			filter.append(models.pointing.id == int(_id))
	if "ids" in args:
		argname = "ids"
		arg = args.get(argname)
		if isinstance(arg, str):
			try:
				arg = str(arg).split('[')[1].split(']')[0].split(',')
			except:
				return make_response(f'Error parsing \{argname}\'. required format is a list: \'[id1, id2...]\'', 500)
		if isinstance(arg, list):
			ids = []
			for i in arg:
				if str(i).isdigit():
					ids.append(int(i))
			filter.append(models.pointing.id.in_(ids))

	if "band" in args:
		band = args.get('band')
		for b in enums.bandpass:
			if b.name == band:
				filter.append(models.pointing.band == b)
	elif "bands" in args:
		argname = "bands"
		arg = args.get(argname)
		if isinstance(arg, str):
			try:
				arg = str(arg).split('[')[1].split(']')[0].split(',')
			except:
				return make_response(f'Error parsing \'{argname}\'. required format is a list: \'[band1, band2...]\'', 500)
		if isinstance(arg, list):
			bands = []
			for b in enums.bandpass:
				if b.name in arg:
					bands.append(b)
			filter.append(models.pointing.band.in_(bands))

	if "status" in args:
		status = args.get('status')
		if "planned" in status:
			filter.append(models.pointing.status == enums.pointing_status.planned)
		elif "completed" in status:
			filter.append(models.pointing.status == enums.pointing_status.completed)
		elif "cancelled" in status:
			filter.append(models.pointing.status == enums.pointing_status.cancelled)
		else:
			return make_response(f"Invalid status: f{status}. Only 'completed', 'planned', and 'cancelled'", 500)
	if "statuses" in args:
		argname = "statuses"
		arg = args.get(argname)
		if isinstance(arg, str):
			try:
				arg = str(arg).split('[')[1].split(']')[0].split(',')
			except:
				return make_response(f'Error parsing \'{argname}\'. required format is a list: \'[status1, status2]\'', 500)
		if isinstance(arg, list):
			statuses = []
			if "planned" in arg:
				statuses.append(enums.pointing_status.planned)
			if "completed" in arg:
				statuses.append(enums.pointing_status.completed)
			if "cancelled" in arg:
				statuses.append(enums.pointing_status.cancelled)
			filter.append(models.pointing.status.in_(statuses))

	if "completed_after" in args:
		time = args.get('completed_after')
		try:
			time = datetime.datetime.strptime(time, "%Y-%m-%dT%H:%M:%S.%f")
		except:
			return make_response("Error parsing date. Should be %Y-%m-%dT%H:%M:%S.%f format. e.g. 2019-05-01T12:00:00.00", 500)
		filter.append(models.pointing.status == enums.pointing_status.completed)
		filter.append(models.pointing.time >= time)

	if "completed_before" in args:
		time = args.get('completed_before')
		try:
			time = datetime.datetime.strptime(time, "%Y-%m-%dT%H:%M:%S.%f")
		except:
			return make_response("Error parsing date. Should be %Y-%m-%dT%H:%M:%S.%f format. e.g. 2019-05-01T12:00:00.00", 500)
		filter.append(models.pointing.status == enums.pointing_status.completed)
		filter.append(models.pointing.time <= time)

	if "planned_after" in args:
		time = args.get('planned_after')
		try:
			time = datetime.datetime.strptime(time, "%Y-%m-%dT%H:%M:%S.%f")
		except:
			return make_response("Error parsing date. Should be %Y-%m-%dT%H:%M:%S.%f format. e.g. 2019-05-01T12:00:00.00", 500)
		filter.append(models.pointing.status == enums.pointing_status.planned)
		filter.append(models.pointing.time >= time)

	if "planned_before" in args:
		time = args.get('planned_before')
		try:
			time = datetime.datetime.strptime(time, "%Y-%m-%dT%H:%M:%S.%f")
		except:
			return make_response("Error parsing date. Should be %Y-%m-%dT%H:%M:%S.%f format. e.g. 2019-05-01T12:00:00.00", 500)
		filter.append(models.pointing.status == enums.pointing_status.planned)
		filter.append(models.pointing.time <= time)

	if "user" in args:
		user = args.get('user')
		if user.isdigit():
			filter.append(models.pointing.submitterid == int(user))
		else:
			filter.append(or_(models.users.username.contains(user),
							  models.users.firstname.contains(user),
							  models.users.lastname.contains(user)))
			filter.append(models.users.id == models.pointing.submitterid)

	if "users" in args:
		argname = "users"
		arg = args.get(argname)
		if isinstance(arg, str):
			try:
				arg = str(arg).split('[')[1].split(']')[0].split(',')
			except:
				return make_response(f'Error parsing \{argname}\'. required format is a list: \'[user1, user2..]\'', 500)
		if isinstance(arg, list):
			ors = []
			for i in arg:
				ors.append(models.users.username.contains(str(i).strip()))
				ors.append(models.users.firstname.contains(str(i).strip()))
				ors.append(models.users.lastname.contains(str(i).strip()))
				if function.isInt(i):
					ors.append(models.pointing.submitterid  == i)
			filter.append(or_(*ors))
			filter.append(models.users.id == models.pointing.submitterid)
		else:
			return make_response(f'Error parsing \{argname}\'. required format is a list: \'[user1, user2, ..]\'', 500)

	if "instrument" in args:
		inst = args.get('instrument')
		if inst.isdigit():
			filter.append(models.pointing.instrumentid == int(inst))
		else:
			filter.append(models.pointing.instrumentid == models.instrument.id)
			filter.append(models.instrument.instrument_name.contains(inst))

	if "instruments" in args:
		argname = "instruments"
		arg = args.get(argname)
		if isinstance(arg, str):
			try:
				arg = str(arg).split('[')[1].split(']')[0].split(',')
			except:
				return make_response(f'Error parsing \{argname}\'. required format is a list: \'[inst1, inst2...]\'', 500)
		if isinstance(arg, list):
			ors = []
			for i in arg:
				ors.append(models.instrument.instrument_name.contains(str(i).strip()))
				ors.append(models.instrument.nickname.contains(str(i).strip()))
				if function.isInt(i):
					ors.append(models.pointing.instrumentid  == i)
			filter.append(or_(*ors))
			filter.append(models.instrument.id == models.pointing.instrumentid)
		else:
			return make_response(f'Error parsing \{argname}\'. required format is a list: \'[inst1, inst2...]\'', 500)

	if 'wavelength_regime' in args and 'wavelength_unit' in args:
		argname = "wavelength_regime"
		arg = args.get(argname)
		try:
			if isinstance(arg, str):
				try:
					arg = str(arg).split('[')[1].split(']')[0].split(',')
				except:
					return make_response(f'Error parsing \{argname}\'. required format is a list: \'[low, high]\'', 500)
			if isinstance(arg, list):
				specmin, specmax = float(arg[0]), float(arg[1])
		except:
			return make_response(f'Error parsing \{argname}\'. required format is a list: \'[low, high]\'', 500)

		try:
			user_unit = args['wavelength_unit']
			spectral_unit = [w for w in enums.wavelength_units if int(w) == user_unit or str(w.name) == user_unit][0]
		except:
			return make_response('wavelength_unit is required, valid units are \'angstrom\', \'nanometer\', and \'micron\'', 500)
		scale = enums.wavelength_units.get_scale(spectral_unit)
		specmin = specmin*scale
		specmax = specmax*scale

		filter.append(models.pointing.inSpectralRange(specmin, specmax, models.SpectralRangeHandler.spectralrangetype.wavelength))

	if 'frequency_regime' in args and 'frequency_unit' in args:
		argname = "frequency_regime"
		arg = args.get(argname)
		try:
			if isinstance(arg, str):
				try:
					arg = str(arg).split('[')[1].split(']')[0].split(',')
				except:
					return make_response(f'Error parsing \{argname}\'. required format is a list: \'[low, high]\'', 500)
			if isinstance(arg, list):
				print(arg)
				specmin, specmax = float(arg[0]), float(arg[1])
		except:
			return make_response(f'Error parsing \{argname}\'. required format is a list: \'[low, high]\'', 500)
		try:
			user_unit = args['frequency_unit']
			spectral_unit = [w for w in enums.frequency_units if int(w) == user_unit or str(w.name) == user_unit][0]
		except:
			return make_response('frequency_unit is required, valid units are \'Hz\', \'kHz\', \'MHz\', \'GHz\', and \'THz\'', 500)
		scale = enums.frequency_units.get_scale(spectral_unit)
		specmin = specmin*scale
		specmax = specmax*scale

		filter.append(models.pointing.inSpectralRange(specmin, specmax, models.SpectralRangeHandler.spectralrangetype.frequency))


	if 'energy_regime' in args and 'energy_unit' in args:
		argname = "energy_regime"
		arg = args.get(argname)
		try:
			if isinstance(arg, str):
				try:
					arg = str(arg).split('[')[1].split(']')[0].split(',')
				except:
					return make_response(f'Error parsing \{argname}\'. required format is a list: \'[low, high]\'', 500)
			if isinstance(arg, list):
				print(arg)
				specmin, specmax = float(arg[0]), float(arg[1])
		except:
			return make_response(f'Error parsing \{argname}\'. required format is a list: \'[low, high]\'', 500)
		try:
			user_unit = args['energy_unit']
			spectral_unit = [w for w in enums.energy_units if int(w) == user_unit or str(w.name) == user_unit][0]
		except:
			return make_response('energy_unit is required, valid units are \'eV\', \'keV\', \'MeV\', \'GeV\', and \'TeV\'', 500)
		scale = enums.energy_units.get_scale(spectral_unit)
		specmin = specmin*scale
		specmax = specmax*scale

		filter.append(models.pointing.inSpectralRange(specmin, specmax, models.SpectralRangeHandler.spectralrangetype.energy))

	if 'depth_gt' in args: #query for brighter things
		depth_gt = args.get('depth_gt')
		user_unit = args.get('depth_unit')
		if function.isFloat(depth_gt):
			try:
				depth_unit = [w for w in enums.depth_unit if int(w) == user_unit or str(w.name) == user_unit][0]
			except:  # noqa: E722
				depth_unit = enums.depth_unit.ab_mag
			if 'mag' in depth_unit.name:
				filter.append(models.pointing.depth <= float(depth_gt))
			elif 'flux' in depth_unit.name:
				filter.append(models.pointing.depth >= float(depth_gt))
		else:
			make_response(f"Error parsing \"depth_gt\": {depth_gt}. Required format is float", 500)

	if 'depth_lt' in args: #query for dimmer things 
		depth_lt = args.get('depth_lt')
		user_unit = args.get('depth_unit')
		if function.isFloat(depth_lt):
			try:
				depth_unit = [w for w in enums.depth_unit if int(w) == user_unit or str(w.name) == user_unit][0]
			except:  # noqa: E722
				depth_unit = enums.depth_unit.ab_mag
			if 'mag' in depth_unit.name:
				filter.append(models.pointing.depth >= float(depth_lt))
			elif 'flux' in depth_unit.name:
				filter.append(models.pointing.depth <= float(depth_lt))
		else:
			make_response(f"Error parsing \"depth_lt\": {depth_lt}. Required format is float", 500)

	pointings = db.session.query(models.pointing).filter(*filter).all()
	pointings = [x.json for x in pointings]

	return make_response(json.dumps(pointings), 200)


@app.route("/api/v0/request_doi", methods=['POST'])
def api_request_doi():

	valid, message, args, user = initial_request_parse(request=request)

	if not valid:
		return make_response(message, 500)

	if 'creators' in args:
		creators = args['creators']
		for c in creators:
			if 'name' not in c.keys() or 'affiliation' not in c.keys():
				return make_response('name and affiliation are required for DOI creators json list', 500)
	elif 'doi_group_id' in args:
		valid, creators = models.doi_author.construct_creators(args['doi_group_id'], user.id)
		if not valid:
			return make_response("Invalid doi_group_id. Make sure you are the User associated with the DOI group", 500)
	else:
		creators = [{ 'name':str(user.firstname) + ' ' + str(user.lastname) }]

	filter=[models.pointing.submitterid == user.id]

	if "graceid" in args:
		graceid = args.get('graceid')
		graceid = models.gw_alert.graceidfromalternate(graceid)
		filter.append(models.pointing_event.graceid == graceid)
		filter.append(models.pointing_event.pointingid == models.pointing.id)

	if "id" in args:
		_id = args.get('id')
		if function.isInt(_id):
			filter.append(models.pointing.id == int(_id))
		else:
			return make_response("Invalid ID", 500)
	elif "ids" in args:
		try:
			ids = args.get('ids')
			filter.append(models.pointing.id.in_(ids))
		except:
			return make_response('Invalid list format of IDs', 500)

	if len(filter) == 0:
		return make_response("Insufficient filter parameters", 500)

	points = db.session.query(models.pointing).filter(*filter).all()

	gids, doi_points, warnings = [], [], []

	for p in points:
		if p.status == enums.pointing_status.completed and p.submitterid == user.id and p.doi_id is None:
			doi_points.append(p)
		else:
			warnings.append("Invalid doi request for pointing: " + str(p.id))

	if len(doi_points) == 0:
		return make_response("No pointings to give DOI", 500)

	insts = db.session.query(models.instrument).filter(models.instrument.id.in_([x.instrumentid for x in doi_points]))
	inst_set = list(set([x.instrument_name for x in insts]))

	gids = list(set([x.graceid for x in db.session.query(models.pointing_event).filter(models.pointing_event.pointingid.in_([x.id for x in doi_points]))]))
	if len(gids) > 1:
		return make_response("Pointings must be only for a single GW event", 500)

	gid = gids[0]

	if 'doi_url' in args:
		doi_id, doi_url = 0, args.get('doi_url')
	else:
		gid = models.gw_alert.alternatefromgraceid(gid)
		doi_id, doi_url = function.create_pointing_doi(points, gid, creators, inst_set)

	if doi_id is not None:
		for p in doi_points:
			p.doi_url = doi_url
			p.doi_id = doi_id

		db.session.flush()
		db.session.commit()

	return make_response(json.dumps({"DOI URL":doi_url, "WARNINGS":warnings}), 200)


@app.route("/api/v0/cancel_all", methods=["POST"])
def cancel_all():
	valid, message, args, user = initial_request_parse(request=request)

	if not valid:
		return make_response(message, 500)

	filter1 = []
	filter1.append(models.pointing.status == enums.pointing_status.planned)
	filter1.append(models.pointing.submitterid == user.id)

	if "graceid" in args:
		graceid = args['graceid']
		graceid = models.gw_alert.graceidfromalternate(graceid)
		filter1.append(models.pointing_event.graceid == graceid)
		filter1.append(models.pointing.id == models.pointing_event.pointingid)
	else:
		return make_response("graceid is required", 500)

	if "instrumentid" in args:
		instid = args['instrumentid']
		if function.isInt(instid):
			filter1.append(models.pointing.instrumentid == instid)
		else:
			return make_response('invalid instrumentid', 500)
	else:
		return make_response('instrumentid is required', 500)

	pointings = db.session.query(models.pointing).filter(*filter1)
	for p in pointings:
		setattr(p, 'status', enums.pointing_status.cancelled)
		setattr(p, 'dateupdated', datetime.datetime.now())

	db.session.commit()
	return make_response("Updated "+str(len(pointings.all()))+" Pointings successfully", 200)


#Cancel PlannedPointing
#Parameters: List of IDs of planned pointings for which it is known that they aren’t going to happen
@app.route("/api/v0/update_pointings", methods=["POST"])
def del_pointings():

	valid, message, args, user = initial_request_parse(request=request)

	if not valid:
		return make_response(message, 500)

	if 'status' in args:
		status = args['status']
		if status not in ['cancelled']:
			return make_response('planned status can only be updated to \'cancelled\'', 500)
	else:
		status = 'cancelled'

	filter1 = []
	filter1.append(models.pointing.status == enums.pointing_status.planned)
	filter1.append(models.pointing.submitterid == user.id)
	try:
		if "id" in args:
			filter1.append(models.pointing.id == int(args.get('id')))
		elif "ids" in args:
			filter1.append(models.pointing.id.in_(json.loads(args.get('ids'))))
		else:
			return make_response('id or ids of pointing event is required', 500)
	except:
		return make_response('There was a problem reading your list of ids', 500)

	if len(filter1) > 0:
		pointings = db.session.query(models.pointing).filter(*filter1)
		itera = 0
		for p in pointings:
			if status == 'cancelled':
				itera = itera + 1
				setattr(p, 'status', enums.pointing_status.cancelled)
				setattr(p, 'dateupdated', datetime.datetime.now())
		db.session.commit()

		return make_response("Updated "+str(itera)+" Pointings successfully", 200)

	else:
		return make_response("Please Don't update the ENTIRE POINTING table", 500)


#Get Instrument/s
#Parameters: List of ID/s, type/s (to be AND’ed).
#Returns: List of Instrument JSON objects
@app.route("/api/v0/instruments", methods=["GET"])
def get_instruments():

	valid, message, args, user = initial_request_parse(request=request)

	if not valid:
		return make_response(message, 500)

	filter=[]

	if "id" in args:
		#validate
		_id = args.get('id')
		filter.append(models.instrument.id == int(_id))
	if "ids" in args:
		#validate
		ids = json.loads(args.get('ids'))
		print(ids)
		filter.append(models.instrument.id.in_(ids))
	if "name" in args:
		name = args.get('name')
		filter.append(models.instrument.instrument_name.contains(name))
	if "names" in args:
		insts = args.get('instruments')
		insts = str(insts).split('[')[1].split(']')[0].split(',')
		ors = []
		for i in insts:
			ors.append(models.instrument.instrument_name.contains(i.strip()))
		filter.append(or_(*ors))
		filter.append(models.instrument.id == models.pointing.instrumentid)

	if "type" in args:
		#validate
		_type = args.get('type')
		filter.append(models.instrument.instrument_type == _type)

	insts = db.session.query(models.instrument).filter(*filter).all()
	insts = [x.json for x in insts]

	return make_response(json.dumps(insts), 200)


@app.route('/api/v0/grb_moc_file', methods=['GET'])
def get_grbmoc():
	'''
	inputs:
		graceid: Can take GW... or S notation
		instruments: [gbm, lat, bat]
	'''

	valid, message, args, user = initial_request_parse(request=request)

	if not valid:
		return make_response(message, 500)

	if "graceid" in args:
		gid = args.get('graceid')
		gid = models.gw_alert.graceidfromalternate(gid)
	else:
		return make_response('graceid is required', 500)

	if "instrument" in args:
		inst = args.get("instrument").lower()
		if inst not in ['gbm', 'lat', 'bat']:
			return make_response('Valid instruments are in [\'gbm\', \'lat\', \'bat\']', 500)
	else:
		return make_response('Instrument is required. Valid instruments are in [\'gbm\', \'lat\', \'bat\']', 500)

	instrument_dictionary = {'gbm':'Fermi', 'lat':'LAT', 'bat':'BAT'}

	moc_filepath = '{}/{}-{}.json'.format('fit', gid, instrument_dictionary[inst])

	try:
		_file = gwtm_io.download_gwtm_file(filename=moc_filepath, source=config.STORAGE_BUCKET_SOURCE, config=config)
		return make_response(_file, 200)
	except:
		return make_response('MOC file for GW-Alert: \'{}\' and instrument: \'{}\' does not exist!'.format(gid, inst), 200)


@app.route('/api/v0/post_alert', methods=['POST'])
def post_alert():

	'''
	inputs:
	'''

	valid, message, args, user = initial_request_parse(request=request)

	if not valid:
		return make_response(message, 500)

	if user.id not in [2]:
			return make_response("Only admin can access this endpoint", 500)

	alert = models.gw_alert.from_json(args)
	db.session.add(alert)

	db.session.flush()
	db.session.commit()

	return make_response(json.dumps(alert.json), 200)


@app.route('/api/v0/query_alerts', methods=['GET'])
def query_alerts():

	valid, message, args, user = initial_request_parse(request=request)

	if not valid:
		return make_response(message, 500)

	filter=[]

	if "graceid" in args:
		graceid = args.get('graceid')
		filter.append(models.gw_alert.graceid == graceid)

	if "alert_type" in args:
		alert_type = args.get('alert_type')
		filter.append(models.gw_alert.alert_type == alert_type)

	alerts = db.session.query(models.gw_alert).filter(*filter).all()
	alerts = [x.json for x in alerts]

	return make_response(json.dumps(alerts), 200)


@app.route('/api/v0/del_test_alerts', methods=['POST'])
def del_test_alerts():
	valid, message, args, user = initial_request_parse(request=request)

	if not valid:
		return make_response(response_message=message, status_code=500)

	if user.id not in [2]:
		return make_response("Only admin can access this endpoint", 500)

	filter = []
	testids = []
	alert_to_keep = "MS181101ab"
	for td in [-1, 0, 1]:
		dd = datetime.datetime.now() + datetime.timedelta(days=td)
		yy = str(dd.year)[2:4]
		mm = dd.month if dd.month >= 10 else f"0{dd.month}"
		dd = dd.day if dd.day >= 10 else f"0{dd.day}"
		graceidlike = f"MS{yy}{mm}{dd}"

		testids.append(graceidlike)
		filter.append(~models.gw_alert.graceid.contains(graceidlike))

	filter.append(~models.gw_alert.graceid.contains(alert_to_keep))
	testids.append(alert_to_keep)
	
	filter.append(models.gw_alert.role == 'test')

	#query for all test alerts that aren't like this one
	gwalerts = db.session.query(models.gw_alert).filter(*filter).all()
	gids_to_rm = [x.graceid for x in gwalerts]

	#query for pointings and pointing events from graceids
	pointing_events = db.session.query(models.pointing_event).filter(models.pointing_event.graceid.in_(gids_to_rm)).all()
	pointing_ids = [x.pointingid for x in pointing_events]
	pointings = db.session.query(models.pointing).filter(models.pointing.id.in_(pointing_ids)).all()

	#query for galaxy lists and galaxy list entries from graceids
	galaxylists = db.session.query(models.gw_galaxy_list).filter(models.gw_galaxy_list.graceid.in_(gids_to_rm)).all()
	galaxylist_ids = [x.id for x in galaxylists]
	galaxyentries = db.session.query(models.gw_galaxy_entry).filter(models.gw_galaxy_entry.listid.in_(galaxylist_ids)).all()

	if len(galaxyentries) > 0:
		print(f"deleting {len(galaxyentries)} galaxy entries")
		for ge in galaxyentries:
			db.session.delete(ge)

	if len(galaxylists) > 0:
		print(f"deleting {len(galaxylists)} galaxy lists")
		for gl in galaxylists:
			db.session.delete(gl)

	if len(pointings) > 0:
		print(f"deleting {len(pointings)} pointing")
		for p in pointings:
			db.session.delete(p)

	if len(pointing_events) > 0:
		print(f"deleting {len(pointing_events)} pointing events")
		for pe in pointing_events:
			db.session.delete(pe)

	if len(gwalerts) > 0:
		print(f"deleting {len(gwalerts)} gwalerts")
		for ga in gwalerts:
			db.session.delete(ga)

	objects = gwtm_io.list_gwtm_bucket(container="test", source=config.STORAGE_BUCKET_SOURCE, config=config)
	objects_to_delete = [
		o for o in objects if not any(t in o for t in testids) and o != 'test/'
	]

	if len(objects_to_delete):
		print(f"deleting {len(objects_to_delete)} from S3")
		tot = 0
		for items in function.by_chunk(objects_to_delete, 1000):
			tot += len(items)
			print(f"bucket chunk: {tot}/{len(objects_to_delete)}")
			gwtm_io.delete_gwtm_files(keys=items, source=config.STORAGE_BUCKET_SOURCE, config=config)

	db.session.commit()

	return make_response('Sucksess', 200)


@app.route('/api/v0/post_icecube_notice', methods=['POST'])
def post_icecube_notice_v0():

	'''
	inputs:
	'''

	valid, message, args, user = initial_request_parse(request=request)

	if not valid:
		return make_response(message, 500)

	if user.id not in [2]:
			return make_response("Only admin can access this endpoint", 500)

	notice_json = args["icecube_notice"]
	notice_events_json = args["icecube_notice_coinc_events"]
	events = []

	notice = models.icecube_notice.from_json(notice_json)
	
	if not notice.already_exists():
		db.session.add(notice)
		db.session.flush()

		for event_json in notice_events_json:
			event = models.icecube_notice_coinc_event.from_json(event_json)
			event.icecube_notice_id = notice.id
			db.session.add(event)
			events.append(event)

		db.session.flush()
		db.session.commit()

		resp = {
			"icecube_notice" : json.dumps(notice.parse),
			"icecube_notice_events" : [json.dumps(x.parse) for x in events]
		}
		return make_response(json.dumps(resp), 200)
	
	resp = {
		"icecube_notice": json.dumps({"message" : "event already exists"}), 
		"icecube_notice_events" : [json.dumps(x.parse) for x in events]
	}
	return make_response(json.dumps(resp), 200)


#Post Candidate/s
#Parameters: List of Candidate JSON objects
#Returns: List of assigned IDs
#Notes: Check if a candidate already exists at these coordinates (with a 2” tolerance) and if so, just add the name to the names table (if new).

#Get Candidate/s
#Parameters: List of ID/s, name/s, group/s, user/s, time/s, RA, Dec (to be AND’ed).
#Returns: List of Candidate JSON objects

#Post Photometry
#Parameters: List of Photometry JSON objects
#Returns: List of assigned IDs

#Get Photometry
#Parameters: List of candidate ID/s, time/s, magnitude/s, filter/s (to be AND’ed).
#Returns: List of Photometry JSON objects

#Post Spectroscopy
#Parameters: List of Spectroscopy JSON objects
#Returns: List of assigned IDs

#Get Spectroscopy
#Parameters: List of candidate ID/s, time/s (to be AND’ed).
#Returns: List of Spectroscopy JSON objects
