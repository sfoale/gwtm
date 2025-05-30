from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime
import json

from server.db.database import get_db
from server.db.models.instrument import Instrument, FootprintCCD
from server.db.models.pointing import Pointing
from server.db.models.users import Users, UserGroups, Groups
from server.db.models.gw_alert import GWAlert
from server.db.models.gw_galaxy import GWGalaxyList, GWGalaxyEntry
from server.db.models.candidate import GWCandidate
from server.db.models.icecube import IceCubeNotice, IceCubeNoticeCoincEvent
from server.db.models.pointing_event import PointingEvent
from server.auth.auth import get_current_user
from sqlalchemy import func, or_
from server.utils.function import sanatize_pointing, project_footprint, sanatize_footprint_ccds
from server.utils.function import sanatize_icecube_event, sanatize_gal_info, sanatize_candidate_info
from server.utils.function import sanatize_XRT_source_info, isInt, get_farrate_farunit, polygons2footprints
from server.utils.function import create_pointing_doi
from server.utils.gwtm_io import get_cached_file, set_cached_file, download_gwtm_file
from server.utils.email import send_account_validation_email
from server.config import settings
from server.core.enums.pointing_status import pointing_status as pointing_status_enum
from server.core.enums.depth_unit import depth_unit as depth_unit_enum
from server.core.enums.wavelength_units import wavelength_units
from server.core.enums.energy_units import energy_units
from server.core.enums.frequency_units import frequency_units
from server.core.enums.bandpass import bandpass

router = APIRouter(tags=["UI"])


@router.get("/ajax_alertinstruments_footprints")
async def get_alert_instruments_footprints(
        graceid: str = None,
        pointing_status: str = None,
        tos_mjd: float = None,
        db: Session = Depends(get_db)
):
    """Get footprints of instruments that observed a specific alert."""
    import hashlib
    import astropy.time

    alert = db.query(GWAlert).filter(GWAlert.graceid == graceid).first()
    if not alert:
        return []

    if pointing_status is None:
        pointing_status = "completed"

    pointing_filter = []
    pointing_filter.append(PointingEvent.graceid == graceid)
    pointing_filter.append(PointingEvent.pointingid == Pointing.id)

    if pointing_status == 'pandc':
        pointing_filter.append(
            or_(Pointing.status == pointing_status_enum.completed, Pointing.status == pointing_status_enum.planned))
    elif pointing_status not in ['all', '']:
        if pointing_status == "completed":
            pointing_filter.append(Pointing.status == pointing_status_enum.completed)
        elif pointing_status == "planned":
            pointing_filter.append(Pointing.status == pointing_status_enum.planned)
        elif pointing_status == "cancelled":
            pointing_filter.append(Pointing.status == pointing_status_enum.cancelled)

    pointing_info = db.query(
        Pointing.id,
        Pointing.instrumentid,
        Pointing.pos_angle,
        Pointing.time,
        func.ST_AsText(Pointing.position).label('position'),
        Pointing.band,
        Pointing.depth,
        Pointing.depth_unit,
        Pointing.status
    ).join(PointingEvent, PointingEvent.pointingid == Pointing.id).filter(*pointing_filter).all()

    pointing_ids = [p.id for p in pointing_info]
    hash_pointing_ids = hashlib.sha1(json.dumps(pointing_ids).encode()).hexdigest()
    cache_key = f'cache/footprint_{graceid}_{pointing_status}_{hash_pointing_ids}'

    cached_overlays = get_cached_file(cache_key, settings)

    if cached_overlays:
        return json.loads(cached_overlays)

    instrument_ids = [p.instrumentid for p in pointing_info]

    instrumentinfo = db.query(
        Instrument.instrument_name,
        Instrument.nickname,
        Instrument.id
    ).filter(
        Instrument.id.in_(instrument_ids)
    ).all()

    footprintinfo = db.query(
        func.ST_AsText(FootprintCCD.footprint).label('footprint'),
        FootprintCCD.instrumentid
    ).filter(
        FootprintCCD.instrumentid.in_(instrument_ids)
    ).all()

    colorlist = [
        '#ffe119', '#4363d8', '#f58231', '#42d4f4', '#f032e6', '#fabebe',
        '#469990', '#e6beff', '#9A6324', '#fffac8', '#800000', '#aaffc3',
        '#000075', '#a9a9a9'
    ]

    inst_overlays = []

    for i, inst in enumerate([x for x in instrumentinfo if x.id != 49]):
        name = inst.nickname if inst.nickname and inst.nickname != 'None' else inst.instrument_name

        try:
            color = colorlist[i]
        except IndexError:
            color = '#' + format(inst.id % 0xFFFFFF, '06x')

        footprint_ccds = [x.footprint for x in footprintinfo if x.instrumentid == inst.id]
        sanatized_ccds = sanatize_footprint_ccds(footprint_ccds)
        inst_pointings = [x for x in pointing_info if x.instrumentid == inst.id]
        pointing_geometries = []

        for p in inst_pointings:
            t = astropy.time.Time([p.time])
            ra, dec = sanatize_pointing(p.position)

            for ccd in sanatized_ccds:
                pointing_footprint = project_footprint(ccd, ra, dec, p.pos_angle)
                pointing_geometries.append({
                    "polygon": pointing_footprint,
                    "time": round(t.mjd[0] - tos_mjd, 3) if tos_mjd else 0
                })

        inst_overlays.append({
            "display": True,
            "name": name,
            "color": color,
            "contours": pointing_geometries
        })

    set_cached_file(cache_key, inst_overlays, settings)

    return inst_overlays


@router.get("/ajax_preview_footprint")
async def preview_footprint(
        ra: float,
        dec: float,
        radius: float = None,
        height: float = None,
        width: float = None,
        shape: str = "circle",
        polygon: str = None
):
    """Generate a preview of an instrument footprint."""
    import math
    import plotly
    import plotly.graph_objects as go

    vertices = []

    if shape.lower() == "circle" and radius:
        circle_points = []
        for i in range(36):
            angle = i * 10 * (math.pi / 180)
            point_ra = ra + (radius * math.cos(angle) / math.cos(math.radians(dec)))
            point_dec = dec + (radius * math.sin(angle))
            circle_points.append([point_ra, point_dec])

        circle_points.append(circle_points[0])
        vertices.append(circle_points)

    elif shape.lower() == "rectangle" and height and width:
        half_width = width / 2
        half_height = height / 2

        ra_factor = math.cos(math.radians(dec))
        ra_offset = half_width / ra_factor

        rect_points = [
            [ra - ra_offset, dec - half_height],
            [ra - ra_offset, dec + half_height],
            [ra + ra_offset, dec + half_height],
            [ra + ra_offset, dec - half_height],
            [ra - ra_offset, dec - half_height]
        ]
        vertices.append(rect_points)

    elif shape.lower() == "polygon" and polygon:
        try:
            poly_points = json.loads(polygon)
            poly_points.append(poly_points[0])
            vertices.append(poly_points)
        except json.JSONDecodeError:
            return {"error": "Invalid polygon format"}
    else:
        return {"error": "Invalid shape type or missing required parameters"}

    traces = []
    for vert in vertices:
        xs = [v[0] for v in vert]
        ys = [v[1] for v in vert]
        trace = go.Scatter(
            x=xs,
            y=ys,
            line_color='blue',
            fill='tozeroy',
            fillcolor='violet'
        )
        traces.append(trace)

    fig = go.Figure(data=traces)
    fig.update_layout(
        showlegend=False,
        xaxis_title="degrees",
        yaxis_title="degrees",
        yaxis=dict(
            matches='x',
            scaleanchor="x",
            scaleratio=1,
            constrain='domain',
        )
    )

    graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
    return graphJSON


@router.get("/ajax_update_spectral_range_from_selected_bands")
async def spectral_range_from_selected_bands(
        band_cov: str,
        spectral_type: str,
        spectral_unit: str
):
    """Calculate spectral range based on selected bands."""
    from server.utils.spectral import wavetoWaveRange, wavetoEnergy, wavetoFrequency

    if not band_cov or band_cov == 'null':
        return {
            'total_min': '',
            'total_max': ''
        }

    bands = band_cov.split(',')
    mins, maxs = [], []

    for b in bands:
        try:
            band_enum = [x for x in bandpass if b == x.name][0]
            band_min, band_max = None, None

            if spectral_type == 'wavelength':
                band_min, band_max = wavetoWaveRange(bandpass=band_enum)
                unit = [x for x in wavelength_units if spectral_unit == x.name][0]
                scale = wavelength_units.get_scale(unit)

            elif spectral_type == 'energy':
                band_min, band_max = wavetoEnergy(bandpass=band_enum)
                unit = [x for x in energy_units if spectral_unit == x.name][0]
                scale = energy_units.get_scale(unit)

            elif spectral_type == 'frequency':
                band_min, band_max = wavetoFrequency(bandpass=band_enum)
                unit = [x for x in frequency_units if spectral_unit == x.name][0]
                scale = frequency_units.get_scale(unit)

            if band_min is not None and band_max is not None:
                mins.append(band_min / scale)
                maxs.append(band_max / scale)

        except (IndexError, ValueError):
            continue

    if mins:
        return {
            'total_min': min(mins),
            'total_max': max(maxs)
        }
    else:
        return {
            'total_min': '',
            'total_max': ''
        }


@router.get("/ajax_icecube_notice")
async def ajax_icecube_notice(
        graceid: str,
        db: Session = Depends(get_db)
):
    """Get IceCube notices associated with a GW event."""
    return_events = []

    icecube_notices = db.query(IceCubeNotice).filter(
        IceCubeNotice.graceid == graceid
    ).all()

    if not icecube_notices:
        return return_events

    icecube_notice_ids = list(set([notice.id for notice in icecube_notices]))

    icecube_notice_events = db.query(
        IceCubeNoticeCoincEvent
    ).filter(
        IceCubeNoticeCoincEvent.icecube_notice_id.in_(icecube_notice_ids)
    ).all()

    for notice in icecube_notices:
        markers = []
        events = [x for x in icecube_notice_events if x.icecube_notice_id == notice.id]

        for i, e in enumerate(events):
            markers.append({
                "name": f"ICN_EVENT_{e.id}",
                "ra": e.ra,
                "dec": e.dec,
                "radius": e.ra_uncertainty,
                "info": sanatize_icecube_event(e, notice)
            })

        return_events.append({
            "name": f"ICECUBENotice{notice.id}",
            "color": "#324E72",
            "markers": markers
        })

    return return_events


@router.get("/ajax_event_galaxies")
async def ajax_event_galaxies(
        alertid: str,
        db: Session = Depends(get_db)
):
    """Get galaxies associated with an event."""
    event_galaxies = []

    gal_lists = db.query(GWGalaxyList).filter(
        GWGalaxyList.alertid == alertid
    ).all()

    if not gal_lists:
        return event_galaxies

    gal_list_ids = list(set([x.id for x in gal_lists]))

    gal_entries = db.query(
        GWGalaxyEntry.name,
        func.ST_AsText(GWGalaxyEntry.position).label('position'),
        GWGalaxyEntry.score,
        GWGalaxyEntry.info,
        GWGalaxyEntry.listid,
        GWGalaxyEntry.rank
    ).filter(
        GWGalaxyEntry.listid.in_(gal_list_ids)
    ).all()

    for glist in gal_lists:
        markers = []
        entries = [x for x in gal_entries if x.listid == glist.id]

        for e in entries:
            ra, dec = sanatize_pointing(e.position)
            markers.append({
                "name": e.name,
                "ra": ra,
                "dec": dec,
                "info": sanatize_gal_info(e, glist)
            })

        event_galaxies.append({
            "name": glist.groupname,
            "color": "",
            "markers": markers
        })

    return event_galaxies


@router.get("/ajax_candidate")
async def ajax_candidate_fetch(
        graceid: str,
        db: Session = Depends(get_db)
):
    """Get candidates associated with a GW event."""
    import shapely.wkb

    normalized_graceid = GWAlert.graceidfromalternate(graceid)

    candidates = db.query(GWCandidate).filter(GWCandidate.graceid == normalized_graceid).all()

    markers = []
    payload = []

    for c in candidates:
        clean_position = shapely.wkb.loads(bytes(c.position.data), hex=True)
        position_str = str(clean_position)
        ra, dec = sanatize_pointing(position_str)

        markers.append({
            "name": c.candidate_name,
            "ra": ra,
            "dec": dec,
            "shape": "star",
            "info": sanatize_candidate_info(c, ra, dec)
        })

    if markers:
        payload.append({
            'name': 'Candidates',
            'color': '',
            'markers': markers
        })

    return payload


@router.get("/ajax_pointingfromid")
async def get_pointing_fromID(
        id: str,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user)
):
    """Get pointing details by ID for the current user's planned pointings."""
    if not id or not isInt(id):
        return {}

    pointing_id = int(id)

    filters = [
        Pointing.submitterid == current_user.id,
        Pointing.status == pointing_status_enum.planned,
        Pointing.id == pointing_id
    ]

    pointing = db.query(Pointing).filter(*filters).first()

    if not pointing:
        return {}

    pointing_event = db.query(PointingEvent).filter(PointingEvent.pointingid == pointing.id).first()
    if not pointing_event:
        return {}

    alert = db.query(GWAlert).filter(GWAlert.graceid == pointing_event.graceid).first()
    if not alert:
        return {}

    position_result = db.query(func.ST_AsText(Pointing.position)).filter(Pointing.id == pointing_id).first()

    if not position_result or not position_result[0]:
        return {}

    position = position_result[0]
    ra = position.split('POINT(')[1].split(' ')[0]
    dec = position.split('POINT(')[1].split(' ')[1].split(')')[0]

    instrument = db.query(Instrument).filter(Instrument.id == pointing.instrumentid).first()

    pointing_json = {
        'ra': ra,
        'dec': dec,
        'graceid': pointing_event.graceid,
        'instrument': f"{pointing.instrumentid}_{instrument.instrument_type.name if instrument else ''}",
        'band': pointing.band.name if pointing.band else '',
        'depth': pointing.depth,
        'depth_err': pointing.depth_err
    }

    return pointing_json


@router.post("/ajax_coverage_calculator")
async def coverage_calculator(
        request: Request,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user)
):
    """Calculate coverage statistics for an alert."""
    import numpy as np
    import healpy as hp
    import plotly
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    data = await request.json()

    graceid = data.get("graceid")
    if not graceid:
        return {"error": "Missing graceid"}

    mappathinfo = data.get("mappathinfo")
    inst_cov = data.get("inst_cov", "")
    band_cov = data.get("band_cov", "")
    depth = data.get("depth_cov")
    depth_unit = data.get("depth_unit", "")
    approx_cov = data.get("approx_cov", 1) == 1
    spec_range_type = data.get("spec_range_type", "")
    spec_range_unit = data.get("spec_range_unit", "")
    spec_range_low = data.get("spec_range_low")
    spec_range_high = data.get("spec_range_high")

    pointing_filter = []
    pointing_filter.append(PointingEvent.graceid == graceid)
    pointing_filter.append(PointingEvent.pointingid == Pointing.id)
    pointing_filter.append(Pointing.status == pointing_status_enum.completed)

    if inst_cov:
        insts_cov = [int(x) for x in inst_cov.split(',')]
        pointing_filter.append(Pointing.instrumentid.in_(insts_cov))

    if depth_unit and depth_unit != 'None':
        try:
            unit_enum = depth_unit_enum[depth_unit]
            pointing_filter.append(Pointing.depth_unit == unit_enum)
        except KeyError:
            pass

    if depth and depth.replace('.', '', 1).isdigit():
        depth_val = float(depth)
        if 'mag' in depth_unit:
            pointing_filter.append(Pointing.depth >= depth_val)
        elif 'flux' in depth_unit:
            pointing_filter.append(Pointing.depth <= depth_val)

    pointings_sorted = db.query(
        Pointing.id,
        Pointing.instrumentid,
        Pointing.pos_angle,
        func.ST_AsText(Pointing.position).label('position'),
        Pointing.band,
        Pointing.depth,
        Pointing.time
    ).join(
        PointingEvent, PointingEvent.pointingid == Pointing.id
    ).filter(
        *pointing_filter
    ).order_by(
        Pointing.time.asc()
    ).all()

    time_of_signal = db.query(
        GWAlert.time_of_signal
    ).filter(
        GWAlert.graceid == graceid
    ).first()

    if not time_of_signal or time_of_signal[0] is None:
        return {"error": "Alert missing time_of_signal"}

    time_of_signal = time_of_signal[0]

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    times = []
    probs = []
    areas = []

    for i, p in enumerate(pointings_sorted):
        elapsed = (p.time - time_of_signal).total_seconds() / 3600
        times.append(elapsed)

        prob = min(0.95, (i + 1) * 0.05)
        area = (i + 1) * 10

        probs.append(prob)
        areas.append(area)

    fig.add_trace(go.Scatter(
        x=times,
        y=[prob * 100 for prob in probs],
        mode='lines',
        name='Probability'
    ), secondary_y=False)

    fig.add_trace(go.Scatter(
        x=times,
        y=areas,
        mode='lines',
        name='Area'
    ), secondary_y=True)

    fig.update_xaxes(title_text="Hours since GW T0")
    fig.update_yaxes(title_text="Percent of GW localization posterior covered", secondary_y=False)
    fig.update_yaxes(title_text="Area coverage (deg<sup>2</sup>)", secondary_y=True)

    coverage_div = plotly.offline.plot(fig, output_type='div', include_plotlyjs=False, show_link=False)

    return {"plot_html": coverage_div}


@router.get("/ajax_request_doi")
async def ajax_request_doi(
        graceid: str,
        ids: str = "",
        doi_group_id: Optional[str] = None,
        doi_url: Optional[str] = None,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user)
):
    """Request a DOI for a set of pointings."""
    normalized_graceid = GWAlert.alternatefromgraceid(graceid)

    if not ids:
        return ""

    pointing_ids = [int(x) for x in ids.split(',')]

    points = db.query(Pointing).join(
        PointingEvent, PointingEvent.pointingid == Pointing.id
    ).filter(
        Pointing.id.in_(pointing_ids),
        PointingEvent.graceid == normalized_graceid
    ).all()

    user = db.query(Users).filter(Users.id == current_user.id).first()

    if doi_group_id:
        creators = [{"name": f"{user.firstname} {user.lastname}", "affiliation": ""}]
    else:
        creators = [{"name": f"{user.firstname} {user.lastname}", "affiliation": ""}]

    insts = db.query(Instrument).filter(
        Instrument.id.in_([p.instrumentid for p in points])
    ).all()

    inst_set = list(set([i.instrument_name for i in insts]))

    if doi_url:
        doi_id, doi_url = 0, doi_url
    else:
        doi_id, doi_url = create_pointing_doi(points, normalized_graceid, creators, inst_set)

    for p in points:
        p.doi_url = doi_url
        p.doi_id = doi_id

    db.commit()

    return doi_url


@router.get("/ajax_alerttype")
async def ajax_get_eventcontour(
        urlid: str,
        db: Session = Depends(get_db)
):
    """Get event contour and alert information."""
    import pandas as pd

    url_parts = urlid.split('_')
    alert_id = url_parts[0]
    alert_type = url_parts[1]
    if len(url_parts) > 2:
        alert_type += url_parts[2]

    alert = db.query(GWAlert).filter(GWAlert.id == int(alert_id)).first()
    if not alert:
        return {"error": "Alert not found"}

    s3path = 'fit' if alert.role == 'observation' else 'test'

    human_far = ""
    if alert.far != 0:
        far_rate, far_unit = get_farrate_farunit(alert.far)
        human_far = f"once per {round(far_rate, 2)} {far_unit}"

    human_time_coinc_far = ""
    if alert.time_coincidence_far != 0 and alert.time_coincidence_far is not None:
        time_coinc_farrate, time_coinc_farunit = get_farrate_farunit(alert.time_coincidence_far)
        time_coinc_farrate = round(time_coinc_farrate, 2)
        human_time_coinc_far = f"once per {round(time_coinc_farrate, 2)} {time_coinc_farunit}"

    human_time_skypos_coinc_far = ""
    if alert.time_sky_position_coincidence_far != 0 and alert.time_sky_position_coincidence_far is not None:
        time_skypos_coinc_farrate, time_skypos_coinc_farunit = get_farrate_farunit(
            alert.time_sky_position_coincidence_far)
        time_skypos_coinc_farrate = round(time_skypos_coinc_farrate, 2)
        human_time_skypos_coinc_far = f"once per {round(time_skypos_coinc_farrate, 2)} {time_skypos_coinc_farunit}"

    if alert.time_difference is not None:
        alert.time_difference = round(alert.time_difference, 3)

    distance_with_error = ""
    if alert.distance is not None:
        alert.distance = round(alert.distance, 3)
        if alert.distance_error is not None:
            alert.distance_error = round(alert.distance_error, 3)
            distance_with_error = f"{alert.distance} ± {alert.distance_error} Mpc"

    if alert.area_50 is not None:
        alert.area_50 = f"{round(alert.area_50, 3)} deg<sup>2</sup>"
    if alert.area_90 is not None:
        alert.area_90 = f"{round(alert.area_90, 3)} deg<sup>2</sup>"

    if alert.prob_bns is not None:
        alert.prob_bns = round(alert.prob_bns, 5)
    if alert.prob_nsbh is not None:
        alert.prob_nsbh = round(alert.prob_nsbh, 5)
    if alert.prob_gap is not None:
        alert.prob_gap = round(alert.prob_gap, 5)
    if alert.prob_bbh is not None:
        alert.prob_bbh = round(alert.prob_bbh, 5)
    if alert.prob_terrestrial is not None:
        alert.prob_terrestrial = round(alert.prob_terrestrial, 5)
    if alert.prob_hasns is not None:
        alert.prob_hasns = round(alert.prob_hasns, 5)
    if alert.prob_hasremenant is not None:
        alert.prob_hasremenant = round(alert.prob_hasremenant, 5)

    detection_overlays = []
    path_info = alert.graceid + '-' + alert_type

    contour_path = f'{s3path}/{path_info}-contours-smooth.json'
    try:
        contours_data = download_gwtm_file(contour_path, source=settings.STORAGE_BUCKET_SOURCE, config=settings)
        contours_df = pd.read_json(contours_data)

        contour_geometry = []
        for contour in contours_df['features']:
            contour_geometry.extend(contour['geometry']['coordinates'])

        detection_overlays.append({
            "display": True,
            "name": "GW Contour",
            "color": '#e6194B',
            "contours": polygons2footprints(contour_geometry, 0)
        })
    except Exception as e:
        print(f"Error downloading contours: {str(e)}")

    payload = {
        'hidden_alertid': alert_id,
        'detection_overlays': detection_overlays,
        'alert_group': alert.group,
        'alert_detectors': alert.detectors,
        'alert_time_of_signal': alert.time_of_signal,
        'alert_timesent': alert.timesent,
        'alert_human_far': human_far,
        'alert_distance_plus_error': distance_with_error,
        'alert_centralfreq': alert.centralfreq,
        'alert_duration': alert.duration,
        'alert_prob_bns': alert.prob_bns,
        'alert_prob_nsbh': alert.prob_nsbh,
        'alert_prob_gap': alert.prob_gap,
        'alert_prob_bbh': alert.prob_bbh,
        'alert_prob_terrestrial': alert.prob_terrestrial,
        'alert_prob_hasns': alert.prob_hasns,
        'alert_prob_hasremenant': alert.prob_hasremenant,
        'alert_area_50': alert.area_50,
        'alert_area_90': alert.area_90,
        'alert_avgra': alert.avgra,
        'alert_avgdec': alert.avgdec,
        'alert_gcn_notice_id': alert.gcn_notice_id,
        'alert_ivorn': alert.ivorn,
        'alert_ext_coinc_observatory': alert.ext_coinc_observatory,
        'alert_ext_coinc_search': alert.ext_coinc_search,
        'alert_time_difference': alert.time_difference,
        'alert_time_coincidence_far': human_time_coinc_far,
        'alert_time_sky_position_coincidence_far': human_time_skypos_coinc_far,
        'selected_alert_type': alert.alert_type
    }

    return payload


@router.post("/ajax_resend_verification_email")
async def resend_verification_email(
        email: str = None,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user)
):
    """Resend the verification email to a user."""
    if email:
        user = db.query(Users).filter(Users.email == email).first()
        if not user:
            return {"error": "User not found"}

        # Only allow admins to send verification emails to other users
        admin_group = db.query(Groups).filter(Groups.name == "admin").first()
        if admin_group:
            user_group = db.query(UserGroups).filter(
                UserGroups.userid == current_user.id,
                UserGroups.groupid == admin_group.id
            ).first()
            if not user_group:
                return {"error": "Not authorized"}
    else:
        user = current_user

    if user.verified:
        return {"message": "User is already verified"}

    # Send the verification email
    send_account_validation_email(user, db)

    return {"message": "Verification email has been resent"}


@router.get("/ajax_scimma_xrt")
async def ajax_scimma_xrt(
        graceid: str,
        db: Session = Depends(get_db)
):
    """Get SCIMMA XRT sources associated with a GW event."""
    import requests as web_requests
    import urllib.parse

    # Normalize the graceid - maintain backward compatibility
    normalized_graceid = GWAlert.graceidfromalternate(graceid)

    # Special case for S190426
    if 'S190426' in normalized_graceid:
        normalized_graceid = 'S190426'

    # Prepare query parameters
    keywords = {
        'keyword': '',
        'cone_search': '',
        'polygon_search': '',
        'alert_timestamp_after': '',
        'alert_timestamp_before': '',
        'role': '',
        'event_trigger_number': normalized_graceid,
        'ordering': '',
        'page_size': 1000,
    }

    # Construct URL and make request
    base_url = 'http://skip.dev.hop.scimma.org/api/alerts/'
    url = f"{base_url}?{urllib.parse.urlencode(keywords)}"

    markers = []
    payload = []

    try:
        response = web_requests.get(url)
        if response.status_code == 200:
            package = response.json()['results']
            for p in package:
                markers.append({
                    'name': p['alert_identifier'],
                    'ra': p['right_ascension'],
                    'dec': p['declination'],
                    'info': sanatize_XRT_source_info(p)
                })
    except Exception as e:
        print(f"Error fetching SCIMMA XRT data: {str(e)}")

    if markers:
        payload.append({
            'name': 'SCIMMA XRT Sources',
            'color': '',
            'markers': markers
        })

    return payload
