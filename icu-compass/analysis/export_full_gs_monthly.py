"""Allocate the full cached strict-GS cohort to an ICU.xlsx scenario, privately.

No source-table scan, network access, live UI changes or modification of ICU.xlsx.
Allocation is a pure function. The portable Pod exporter clones OOXML template
parts with Python's standard library, retaining original fills and cell positions.
This is a virtual scenario assignment, never actual pooled hospital occupancy.
"""
import argparse
import copy
import csv
import hashlib
import json
import os
import re
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import select_gs_scenarios as selection
from monthly_plan import normalized_rows, parse_workbook_plan, segment_episodes

NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'
CONTENT = 'http://schemas.openxmlformats.org/package/2006/content-types'
ET.register_namespace('', NS)
ET.register_namespace('r', REL)
KNOWN = {'ER': ('ed_within_24h_before_icu',),
         'OP': ('surgery_ended_before_icu_24h', 'surgery_record_during_icu'),
         'DEATH': ('death_during_icu',)}
COLORS = {'FF0000': 'red', '0070C0': 'blue', '00B050': 'green', 'FFFF00': 'yellow'}
POLICY = ('Virtual scenario assignment, not actual concurrent hospital occupancy. '
          'Workbook days, colors and length of stay remain fictional plan values. '
          'ER means ED recorded within 24 hours before ICU, not a proven direct transfer. '
          'CPR is unverified in this cached-cohort allocation. GW, AE and OR are undefined or unconfirmed. '
          'Every allocated episode uses a distinct hospital-subject across all generated sheets.')


def tag(name):
    return '{' + NS + '}' + name


def xbytes(element):
    # Drop only compatibility hints whose declaration prefixes ElementTree does
    # not retain. Original template parts are kept byte-for-byte separately.
    for node in element.iter():
        node.attrib.pop('{http://schemas.openxmlformats.org/markup-compatibility/2006}Ignorable', None)
    # OPC readers require unprefixed Types/Relationships in their own default
    # namespaces. Select the root namespace for each independently saved part.
    ET.register_namespace('', element.tag.split('}')[0][1:])
    return ET.tostring(element, encoding='utf-8', xml_declaration=True)


def cell_value(cell, strings):
    if cell is None:
        return ''
    if cell.get('t') == 'inlineStr':
        return ''.join(node.text or '' for node in cell.iter(tag('t')))
    value = cell.findtext(tag('v'), '')
    return strings[int(value)] if cell.get('t') == 's' and value else value


def workbook_rows(path):
    """Read the supplied A:I layout and its actual fill colors without Excel."""
    with zipfile.ZipFile(path) as archive:
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(n.text or '' for n in item.iter(tag('t')))
                       for item in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        styles = ET.fromstring(archive.read('xl/styles.xml'))
        fills = list(styles.find(tag('fills')))
        xfs = list(styles.find(tag('cellXfs')))
        sheet = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        rows = []
        for record in sheet.find(tag('sheetData')):
            number = int(record.get('r'))
            if number == 1:
                continue
            cells = {cell.get('r'): cell for cell in record.findall(tag('c'))}
            day = cell_value(cells.get('A' + str(number)), strings)
            if not day and not any(chr(66 + bed) + str(number) in cells for bed in range(8)):
                continue
            beds = []
            for bed in range(8):
                cell = cells.get(chr(66 + bed) + str(number))
                fill = fills[int(xfs[int(cell.get('s', '0'))].get('fillId', '0'))] if cell is not None else None
                color = fill.find('.//' + tag('fgColor')) if fill is not None else None
                rgb = color.get('rgb', '')[-6:].upper() if color is not None else ''
                if rgb and rgb not in COLORS and rgb not in ('FFFFFF', '000000'):
                    raise ValueError('Unrecognized original workbook fill; refuse to infer occupancy')
                beds.append({'status': COLORS.get(rgb, 'empty'), 'event': cell_value(cell, strings).strip()})
            rows.append({'day': int(float(day)) if day else None, 'sourceRow': number, 'beds': beds})
    normalized_rows(rows)
    return rows


def load_cohort(path, expected=14321):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != expected:
        raise ValueError('Strict GS input count does not match expected count')
    seen = set()
    for row in rows:
        for field in ('SUBJECT_ID', 'HADM_ID', 'STAY_ID'):
            row[field] = selection.gs.ident(row.get(field))
        identity = selection.key(row)
        start, end, entered = (selection.gs.dt(row.get(field)) for field in ('icu_in', 'icu_out', 'gs_entry_at'))
        if (identity in seen or not all(identity) or row['hospital'] not in selection.gs.HOSPITALS
                or not start or not end or start >= end or row.get('gs_entry_code') != 'GS'
                or not entered or entered > start):
            raise ValueError('Strict GS CSV contains invalid or duplicate source evidence')
        seen.add(identity)
        row['gs_entry_evidence'] = {'table': 'SERVICES', 'code': 'GS', 'at': entered.isoformat(),
                                    'source_partitions': selection.parts(row.get('gs_entry_source_partitions'))}
    return rows


def prepare_candidates(candidates):
    prepared = []
    for raw in candidates:
        row = copy.deepcopy(raw)
        # Revalidate cached source tables and half-open ICU intervals even when
        # called directly by tests or another script.
        evidence = selection.verified_evidence(row, row.get('evidence', {}))
        row['evidence'] = {kind: event for kind, event in evidence.items()
                           if any(kind in kinds for kinds in KNOWN.values())}
        row['_tokens'] = {token for token, kinds in KNOWN.items() if any(kind in row['evidence'] for kind in kinds)}
        row['_los_days'] = (selection.gs.dt(row['icu_out']) - selection.gs.dt(row['icu_in'])).total_seconds() / 86400
        row['_key'] = selection.key(row)
        row['_subject'] = (row['hospital'], selection.gs.ident(row['SUBJECT_ID']))
        row['_tie'] = hashlib.sha256('|'.join(row['_key']).encode()).hexdigest()
        prepared.append(row)
    return prepared


def allocate_scope(prepared, rows, scope, used_subjects=None):
    """Pure allocation: input rows/candidates/set are never mutated."""
    days, undated = normalized_rows(rows)
    episodes = segment_episodes(days)
    used = set(used_subjects or ())
    counts = Counter()
    # Allocate the rarest positive-evidence requirements before abundant OP.
    def eligible(episode, row):
        requested = {e['event'].upper() for e in episode['events']}
        if ('DEATH' in requested and 'DEATH' not in row['_tokens']) or ('GW' in requested and 'DEATH' in row['_tokens']):
            return set()
        return requested & row['_tokens'] & KNOWN.keys()
    episode_candidates = {episode['episode_id']: [(row, eligible(episode, row)) for row in prepared] for episode in episodes}
    episode_candidates = {key: [(row, matched) for row, matched in options if matched] for key, options in episode_candidates.items()}
    def priority(episode):
        options = episode_candidates[episode['episode_id']]
        requested = {e['event'].upper() for e in episode['events']}
        return (len(options), -len(requested & KNOWN.keys()), episode['start_day'], episode['bed'])
    for episode in sorted(episodes, key=priority):
        requested = {e['event'].upper() for e in episode['events']}
        duration = episode['end_day'] - episode['start_day'] + 1
        options = [(row, matched) for row, matched in episode_candidates[episode['episode_id']] if row['_subject'] not in used]
        def score(option):
            row, matched = option
            return (-int(matched == requested & KNOWN.keys()), -len(matched),
                    abs(row['_los_days'] - duration), counts[row['hospital']], row['_tie'])
        episode.update(scope=scope, plan_duration_days=duration, plan_colors_verified=False,
                       plan_timing_verified=False, reused_patient=False)
        if options:
            row, matched = min(options, key=score)
            missing = sorted(requested - matched)
            evidence = {kind: event for kind, event in row['evidence'].items()
                        if any(kind in KNOWN[token] for token in matched)}
            episode.update(match_status='partial' if missing else 'matched', matched_criteria=sorted(matched),
                           unconfirmed_criteria=missing, source_hospital=row['hospital'], actual_icu_los_days=round(row['_los_days'], 5),
                           absolute_los_difference_days=round(abs(row['_los_days'] - duration), 5),
                           source_identity={field: row[field] for field in ('hospital', 'SUBJECT_ID', 'HADM_ID', 'STAY_ID')},
                           source_partitions=selection.parts(row.get('source_partitions')), source_icu_in=row['icu_in'],
                           source_icu_out=row['icu_out'], gs_entry_evidence=copy.deepcopy(row.get('gs_entry_evidence', {})),
                           candidate_evidence=evidence)
            used.add(row['_subject'])
            counts[row['hospital']] += 1
        else:
            episode.update(match_status='unlinked', matched_criteria=[], unconfirmed_criteria=sorted(requested),
                           source_identity=None, source_hospital=None, candidate_evidence={})
    # Chronological aliases are unrelated to source identifiers.
    for index, episode in enumerate(sorted(episodes, key=lambda e: (e['start_day'], e['bed'])), 1):
        episode['case_alias'] = f'{scope}-P{index:03d}' if episode['source_identity'] else None
        for day in days:
            if day['day'] not in episode['cell_days']:
                continue
            cell = day['beds'][episode['bed'] - 1]
            token = cell['event'].upper()
            cell.update(episode_id=episode['episode_id'], case_alias=episode['case_alias'],
                        match_status=episode['match_status'], source_hospital=episode['source_hospital'],
                        event_verified=token in episode['matched_criteria'] if token else None,
                        matched_criteria=episode['matched_criteria'], unconfirmed_criteria=episode['unconfirmed_criteria'])
    for day in days:
        for cell in day['beds']:
            if cell['status'] in ('empty', 'yellow'):
                cell.update(case_alias=None, episode_id=None, match_status='reserved' if cell['status'] == 'yellow' else 'empty')
    totals = Counter(e['match_status'] for e in episodes)
    return {'scope': scope, 'days': days, 'undated_rows': undated, 'episodes': episodes,
            'summary': {'episodes': len(episodes), 'matched': totals['matched'], 'partial': totals['partial'],
                        'unlinked': totals['unlinked'], 'unique_patients': len(episodes) - totals['unlinked'],
                        'source_hospitals': dict(counts)}}, used


def build_catalog(candidates, rows, include_virtual=True):
    prepared = prepare_candidates(candidates)
    scopes, used = {}, set()
    if include_virtual:
        scopes['VIRTUAL'], used = allocate_scope(prepared, rows, 'VIRTUAL', used)
    for hospital in sorted({row['hospital'] for row in prepared}):
        name = 'H' + hospital
        scopes[name], used = allocate_scope([row for row in prepared if row['hospital'] == hospital], rows, name, used)
    totals = Counter()
    for scope in scopes.values():
        totals.update({key: scope['summary'][key] for key in ('episodes', 'matched', 'partial', 'unlinked')})
    return {'schema_version': 'full-gs-monthly-allocation-v1', 'generated_at': datetime.now(timezone.utc).isoformat(),
            'policy': POLICY, 'cohort_stays': len(candidates), 'scopes': scopes,
            'summary': {**dict(totals), 'unique_patients': len(used), 'scope_count': len(scopes)}}


def write_cell(sheet, address, value, style=None):
    data = sheet.find(tag('sheetData'))
    rownum = int(re.search(r'\d+', address)[0])
    row = next((r for r in data if int(r.get('r')) == rownum), None)
    if row is None:
        row = ET.SubElement(data, tag('row'), {'r': str(rownum)})
    cell = next((c for c in row if c.get('r') == address), None)
    if cell is None:
        cell = ET.SubElement(row, tag('c'), {'r': address})
    for child in list(cell):
        cell.remove(child)
    if style is not None:
        cell.set('s', str(style))
    if isinstance(value, (int, float)):
        cell.attrib.pop('t', None)
        ET.SubElement(cell, tag('v')).text = str(value)
    else:
        cell.set('t', 'inlineStr')
        ET.SubElement(ET.SubElement(cell, tag('is')), tag('t')).text = str(value)


def simple_sheet(records, widths=None):
    sheet = ET.Element(tag('worksheet'))
    ET.SubElement(sheet, tag('dimension'), {'ref': f'A1:{column_name(max(map(len, records)))}{len(records)}'})
    if widths:
        cols = ET.SubElement(sheet, tag('cols'))
        for index, width in enumerate(widths, 1):
            ET.SubElement(cols, tag('col'), {'min': str(index), 'max': str(index), 'width': str(width), 'customWidth': '1'})
    ET.SubElement(sheet, tag('sheetData'))
    for row, values in enumerate(records, 1):
        for col, value in enumerate(values, 1):
            write_cell(sheet, column_name(col) + str(row), value if value is not None else '')
    return sheet


def column_name(number):
    name = ''
    while number:
        number, remainder = divmod(number - 1, 26)
        name = chr(65 + remainder) + name
    return name


def fallback_package(rows):
    """Fallback retains parsed colors/coordinates, not unavailable Excel styles."""
    styles = ET.Element(tag('styleSheet'))
    fonts = ET.SubElement(styles, tag('fonts'), {'count': '1'})
    font = ET.SubElement(fonts, tag('font'))
    ET.SubElement(font, tag('sz'), {'val': '11'})
    ET.SubElement(font, tag('name'), {'val': 'Calibri'})
    fills = ET.SubElement(styles, tag('fills'), {'count': '6'})
    for kind in ('none', 'gray125'):
        ET.SubElement(ET.SubElement(fills, tag('fill')), tag('patternFill'), {'patternType': kind})
    for rgb in COLORS:
        pattern = ET.SubElement(ET.SubElement(fills, tag('fill')), tag('patternFill'), {'patternType': 'solid'})
        ET.SubElement(pattern, tag('fgColor'), {'rgb': 'FF' + rgb})
    borders = ET.SubElement(styles, tag('borders'), {'count': '1'})
    ET.SubElement(borders, tag('border'))
    stylexfs = ET.SubElement(styles, tag('cellStyleXfs'), {'count': '1'})
    ET.SubElement(stylexfs, tag('xf'), {'numFmtId': '0', 'fontId': '0', 'fillId': '0', 'borderId': '0'})
    xfs = ET.SubElement(styles, tag('cellXfs'), {'count': '5'})
    for fill in (0, 2, 3, 4, 5):
        ET.SubElement(xfs, tag('xf'), {'numFmtId': '0', 'fontId': '0', 'fillId': str(fill), 'borderId': '0', 'xfId': '0'})
    workbook = ET.Element(tag('workbook'))
    sheets = ET.SubElement(workbook, tag('sheets'))
    ET.SubElement(sheets, tag('sheet'), {'name': 'Original plan fallback', 'sheetId': '1', '{' + REL + '}id': 'rId1'})
    rels = ET.Element('{' + PKG + '}Relationships')
    ET.SubElement(rels, '{' + PKG + '}Relationship', {'Id': 'rId1', 'Type': REL + '/worksheet', 'Target': 'worksheets/sheet1.xml'})
    ET.SubElement(rels, '{' + PKG + '}Relationship', {'Id': 'rId2', 'Type': REL + '/styles', 'Target': 'styles.xml'})
    types = ET.Element('{' + CONTENT + '}Types')
    ET.SubElement(types, '{' + CONTENT + '}Default', {'Extension': 'rels', 'ContentType': 'application/vnd.openxmlformats-package.relationships+xml'})
    ET.SubElement(types, '{' + CONTENT + '}Default', {'Extension': 'xml', 'ContentType': 'application/xml'})
    for path, suffix in (('/xl/workbook.xml', 'sheet.main+xml'), ('/xl/styles.xml', 'styles+xml'), ('/xl/worksheets/sheet1.xml', 'worksheet+xml')):
        ET.SubElement(types, '{' + CONTENT + '}Override', {'PartName': path, 'ContentType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.' + suffix})
    rootrels = ET.Element('{' + PKG + '}Relationships')
    ET.SubElement(rootrels, '{' + PKG + '}Relationship', {'Id': 'rId1', 'Type': REL + '/officeDocument', 'Target': 'xl/workbook.xml'})
    template = simple_sheet([['Day'] + ['Bed ' + str(i) for i in range(1, 9)]], [9] + [15] * 8)
    indices = {'empty': 0, 'red': 1, 'blue': 2, 'green': 3, 'yellow': 4}
    for row in rows:
        at = row['sourceRow']
        write_cell(template, 'A' + str(at), row['day'] if row['day'] is not None else '')
        for index, cell in enumerate(row['beds'], 2):
            write_cell(template, column_name(index) + str(at), cell['event'], indices[cell['status']])
    template.find(tag('dimension')).set('ref', 'A1:I' + str(max(row['sourceRow'] for row in rows)))
    return {'[Content_Types].xml': xbytes(types), '_rels/.rels': xbytes(rootrels),
            'xl/workbook.xml': xbytes(workbook), 'xl/_rels/workbook.xml.rels': xbytes(rels),
            'xl/styles.xml': xbytes(styles), 'xl/worksheets/sheet1.xml': xbytes(template)}


def export_xlsx(path, catalog, rows, template_path=None):
    """Clone the source worksheet and style parts; raw IDs stay in private JSON."""
    path = Path(path)
    if template_path and path.resolve() == Path(template_path).resolve():
        raise ValueError('Output must not overwrite original workbook')
    if template_path:
        with zipfile.ZipFile(template_path) as archive:
            package = {name: archive.read(name) for name in archive.namelist()}
    else:
        package = fallback_package(rows)
    original_sheet = package['xl/worksheets/sheet1.xml']
    original_styles = package['xl/styles.xml']
    styles = ET.fromstring(original_styles)
    xfs = styles.find(tag('cellXfs'))
    wrapped_styles = {}
    for index, original in enumerate(list(xfs)):
        wrapped = copy.deepcopy(original)
        wrapped.set('fontId', '0')
        alignment = wrapped.find(tag('alignment'))
        if alignment is None:
            alignment = ET.SubElement(wrapped, tag('alignment'))
        alignment.set('wrapText', '1')
        alignment.set('vertical', 'center')
        alignment.set('horizontal', 'center')
        wrapped_styles[index] = len(xfs)
        xfs.append(wrapped)
    xfs.set('count', str(len(xfs)))
    package['xl/styles.xml'] = xbytes(styles)
    original_workbook = package['xl/workbook.xml']
    workbook = ET.fromstring(original_workbook)
    rels = ET.fromstring(package['xl/_rels/workbook.xml.rels'])
    types = ET.fromstring(package['[Content_Types].xml'])
    sheets = workbook.find(tag('sheets'))
    max_sheet = max(int(s.get('sheetId')) for s in sheets)
    max_rel = max(int(r.get('Id')[3:]) for r in rels if re.fullmatch(r'rId\d+', r.get('Id', '')))
    added = []
    notes = [['Scope', 'Episode', 'Alias', 'Bed', 'Plan start day', 'Plan end day', 'Match',
              'Confirmed similarities', 'Unconfirmed criteria', 'Source hospital', 'Actual ICU LOS (days)',
              'Planned duration (days)', 'LOS difference (days)', 'Evidence tables', 'Interpretation']]
    for name, scope in catalog['scopes'].items():
        sheet = ET.fromstring(original_sheet)
        # Copies retain the eight-bed layout and all source fills. Added alias
        # lines need readable dimensions; the untouched original remains exact.
        existing_cols = sheet.find(tag('cols'))
        if existing_cols is not None:
            sheet.remove(existing_cols)
        cols = ET.Element(tag('cols'))
        ET.SubElement(cols, tag('col'), {'min': '1', 'max': '1', 'width': '9', 'customWidth': '1'})
        ET.SubElement(cols, tag('col'), {'min': '2', 'max': '9', 'width': '19', 'customWidth': '1'})
        sheet.insert(list(sheet).index(sheet.find(tag('sheetData'))), cols)
        for row in sheet.find(tag('sheetData')):
            row.set('ht', '46')
            row.set('customHeight', '1')
            for cell in row.findall(tag('c')):
                cell.set('s', str(wrapped_styles[int(cell.get('s', '0'))]))
        for day in scope['days']:
            for bed, cell in enumerate(day['beds'], 2):
                if not cell.get('episode_id'):
                    continue
                text = cell['event'] or 'Continue'
                text += '\n' + (cell['case_alias'] or 'UNLINKED')
                if cell['event'] and not cell.get('event_verified'):
                    text += '\nUnconfirmed'
                write_cell(sheet, column_name(bed) + str(day['sourceRow']), text)
        # Added rows leave every original coordinate and fill unchanged.
        last = max(row['sourceRow'] for row in rows)
        for offset, message in enumerate([name + ' — virtual scenario', POLICY,
                                          'See Matching notes for episode-level evidence and LOS comparison.',
                                          'The final four undated source rows are retained without invented patient assignments.'], 3):
            write_cell(sheet, 'A' + str(last + offset), message)
        sheet.find(tag('dimension')).set('ref', 'A1:I' + str(last + 6))
        for view in sheet.findall('.//' + tag('sheetView')):
            view.attrib.pop('tabSelected', None)
            view.set('zoomScale', '85')
        added.append((name + ' scenario', sheet, True))
        for episode in scope['episodes']:
            notes.append([name, episode['episode_id'], episode['case_alias'], episode['bed'], episode['start_day'], episode['end_day'],
                          episode['match_status'], ', '.join(episode['matched_criteria']), ', '.join(episode['unconfirmed_criteria']),
                          episode['source_hospital'], episode.get('actual_icu_los_days'), episode['plan_duration_days'],
                          episode.get('absolute_los_difference_days'), ', '.join(sorted({e['table'] for e in episode['candidate_evidence'].values()})),
                          'Colors and dates are fictional; same alias across a continued episode.'])
    added.append(('Matching notes', simple_sheet(notes, [13, 12, 21, 7, 15, 15, 13, 27, 27, 17, 22, 24, 22, 28, 82]), False))
    for index, (name, sheet, cloned) in enumerate(added, 1):
        number, relationship = max_sheet + index, 'rId' + str(max_rel + index)
        target = f'xl/worksheets/sheet{number}.xml'
        ET.SubElement(sheets, tag('sheet'), {'name': name[:31], 'sheetId': str(number), '{' + REL + '}id': relationship})
        ET.SubElement(rels, '{' + PKG + '}Relationship', {'Id': relationship, 'Type': REL + '/worksheet', 'Target': f'worksheets/sheet{number}.xml'})
        ET.SubElement(types, '{' + CONTENT + '}Override', {'PartName': '/' + target,
                      'ContentType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'})
        package[target] = xbytes(sheet)
        source_rels = 'xl/worksheets/_rels/sheet1.xml.rels'
        if cloned and source_rels in package:
            package[f'xl/worksheets/_rels/sheet{number}.xml.rels'] = package[source_rels]
    # Preserve original extension/compatibility prefix declarations in the
    # workbook. ElementTree cannot preserve prefixes referenced as text in
    # mc:Choice Requires attributes from Excel's original metadata.
    ET.register_namespace('', NS)
    serialized_sheets = ET.tostring(sheets, encoding='unicode')
    package['xl/workbook.xml'] = re.sub(r'<sheets(?:\s[^>]*)?>.*?</sheets>',
                                       lambda _: serialized_sheets,
                                       original_workbook.decode('utf-8'), count=1, flags=re.S).encode('utf-8')
    package['xl/_rels/workbook.xml.rels'] = xbytes(rels)
    package['[Content_Types].xml'] = xbytes(types)
    temp = path.with_suffix('.tmp')
    with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'wb') as handle:
        with zipfile.ZipFile(handle, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, value in package.items():
                archive.writestr(name, value)
    temp.chmod(0o600)
    temp.replace(path)
    # Original worksheet and style parts must remain identical after export.
    with zipfile.ZipFile(path) as archive:
        assert archive.read('xl/worksheets/sheet1.xml') == original_sheet
        # Existing style records retain order and content; only copies append.
        saved_xfs = ET.fromstring(archive.read('xl/styles.xml')).find(tag('cellXfs'))
        old_xfs = ET.fromstring(original_styles).find(tag('cellXfs'))
        assert [ET.tostring(x) for x in list(saved_xfs)[:len(old_xfs)]] == [ET.tostring(x) for x in old_xfs]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    runtime = '/home/khdp-user/workspace/icu-runtime'
    parser.add_argument('--cohort', default=os.getenv('KMIMIC_GS_COHORT', runtime + '/gs-scenario-selection/gs_at_entry_stays.csv'))
    parser.add_argument('--extraction', default=os.getenv('KMIMIC_EXTRACTION', runtime + '/full-kmimic-extract'))
    parser.add_argument('--workbook', default=os.getenv('KMIMIC_PLAN_XLSX', runtime + '/ICU.xlsx'))
    parser.add_argument('--plan-js', default=os.getenv('KMIMIC_PLAN_JS', str(Path(__file__).resolve().parents[1] / 'static/workbook-plan.js')))
    parser.add_argument('--out', default=os.getenv('KMIMIC_GS_MONTHLY_OUT', runtime + '/full-gs-monthly-allocation'))
    parser.add_argument('--expected-gs', type=int, default=14321)
    args = parser.parse_args()
    out, workbook = Path(args.out), Path(args.workbook)
    out.mkdir(parents=True, exist_ok=True)
    out.chmod(0o700)
    template = workbook if workbook.is_file() else None
    rows = workbook_rows(template) if template else parse_workbook_plan(Path(args.plan_js).read_text())
    candidates = load_cohort(args.cohort, args.expected_gs)
    evidence_audits, _ = selection.add_evidence(candidates, Path(args.extraction), out / 'CPR_CACHE_NOT_USED')
    catalog = build_catalog(candidates, rows)
    catalog['evidence_audits'] = evidence_audits
    catalog['template'] = {'original_available': bool(template), 'formatting_preserved': bool(template),
                           'source_sha256': hashlib.sha256(template.read_bytes()).hexdigest() if template else None,
                           'fallback_note': None if template else 'Original workbook unavailable; JS-derived layout and colors only.'}
    selection.gs.write_json(out / 'monthly_catalog.private.json', catalog)
    export_xlsx(out / 'GS_monthly_plan.private.xlsx', catalog, rows, template)
    summary = {**catalog['summary'], 'cohort_stays': len(candidates),
               'by_scope': {key: value['summary'] for key, value in catalog['scopes'].items()},
               'template_formatting_preserved': bool(template), 'evidence_audits': evidence_audits}
    selection.gs.write_json(out / 'summary.json', summary)
    print('GS_MONTHLY_DONE', json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
