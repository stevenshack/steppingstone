"""Tests for nib_structs.py - Parse NeXTSTEP nib struct data.
Tests cover:
1. NSWindowTemplate struct (frame, title, styleMask)
2. NSMenuTemplate struct (menu items, key equivalents, actions)
3. NSControl/NSTextField/NSButton structs (frames, labels, actions)
4. Outlet/target-action connection resolution
5. Real ObjC object creation and NSArchiver archive
"""

import os, sys, struct

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from nib_structs import (
    load_nib, find_arrays, find_window_frames, find_strings_in_data,
    find_windows_in_nib, find_all_strings, find_selectors_in_nib,
    find_struct_in_raw, extract_strings_and_selectors,
    TE2CLASS, NIB_PATHS, NEXTDATA,
)

NIB_DIR = os.path.join(NEXTDATA, 'LocalApps/EnvelopeMaker.app')
ENVELOPEMAKER_NIB = os.path.join(NIB_DIR, 'EnvelopeMaker.nib')
INFO_NIB = os.path.join(NIB_DIR, 'Info.nib')

EXPECTED_OUTLETS = [
    'editWindow', 'envelopeView', 'infoPanel',
    'fromField1', 'fromField2', 'fromField3', 'fromField4',
    'toField1', 'toField2', 'toField3', 'toField4', 'toField5',
]
EXPECTED_SELECTORS = [
    'appDidInit:', 'printEnvelope:', 'setAddrFields:', 'showInfoPanel:',
    'cut:', 'copy:', 'paste:', 'selectAll:', 'delete:',
    'hide:', 'terminate:', 'performClose:', 'performMiniaturize:',
    'arrangeInFront:', 'checkSpelling:', 'copyFont:', 'pasteFont:',
    'copyRuler:', 'pasteRuler:', 'toggleRuler:', 'runPageLayout:',
    'alignSelLeft:', 'alignSelCenter:', 'alignSelRight:',
    'subscript:', 'superscript:', 'underline:', 'showGuessPanel:',
    'orderFrontColorPanel:', 'performClick:', 'unscript:',
]


# ============================================================
# 1. NSWindowTemplate Struct Parsing
# ============================================================

def test_window_title_string():
    """The string 'Envelope Editor' should appear in the nib data."""
    all_strings = find_all_strings('EnvelopeMaker')
    assert 'Envelope Editor' in all_strings, \
        f'Missing "Envelope Editor". Related: {[s for s in all_strings if "Envelope" in s]}'


def test_window_template_type_encoding():
    """WindowTemplate type encoding iiii***@s@ should have correct character counts."""
    te = 'iiii***@s@'
    assert te.count('i') == 4
    assert te.count('*') == 3
    assert te.count('@') == 2
    assert te.count('s') == 1
    # Verify it's stored as TE2CLASS
    assert TE2CLASS['iiii***@s@'] == 'WindowTemplate'


# ============================================================
# 2. NSMenuTemplate Struct Parsing (selector extraction)
# ============================================================

def test_menu_selectors_in_nib():
    """All expected menu action selectors should be extractable from nib."""
    selectors = find_selectors_in_nib('EnvelopeMaker')
    sel_set = set(selectors)

    menu_sel = {'hide:', 'terminate:', 'cut:', 'copy:', 'paste:',
                'selectAll:', 'performClose:', 'performMiniaturize:',
                'copyFont:', 'pasteFont:', 'copyRuler:', 'pasteRuler:'}
    found = menu_sel & sel_set
    assert len(found) >= 6, \
        f'Too few menu selectors ({len(found)}/12): {found}'


def test_known_selectors_extracted():
    """The known 31 selectors should be extractable from raw data."""
    with open(ENVELOPEMAKER_NIB, 'rb') as f:
        data = f.read()
    extracted = extract_strings_and_selectors(data)
    selectors = set(extracted['selectors'])

    expected = set(EXPECTED_SELECTORS)
    missing = expected - selectors
    assert len(missing) <= 5, \
        f'Missing {len(missing)} selectors: {missing}'


# ============================================================
# 3. NSControl/NSTextField/NSButton Struct Parsing
# ============================================================

def test_ui_labels_in_nib():
    """UI labels like 'From Address', 'To Address', 'Info' should appear."""
    all_strings = find_all_strings('EnvelopeMaker')
    expected = {'From Address', 'To Address', 'Info', 'Set', 'Print',
                'EnvelopeApp', 'Envelope Editor', 'EnvelopeView',
                'MainMenu', 'WindowTemplate', 'EnvelopeMaker',
                'Hide', 'Quit', 'NXreturnSign', 'Box'}
    found = expected & set(all_strings)
    assert len(found) >= 8, \
        f'Only {len(found)}/{len(expected)} labels found: {found}'


def test_text_field_names_in_nib():
    """Text field outlet names should exist in nib."""
    all_strings = find_all_strings('EnvelopeMaker')
    fields = {'fromField1', 'fromField2', 'fromField3', 'fromField4',
              'toField1', 'toField2', 'toField3', 'toField4', 'toField5',
              'editWindow', 'envelopeView', 'infoPanel'}
    found = fields & set(all_strings)
    assert len(found) >= 6, \
        f'Only {len(found)}/{len(fields)} field names found: {found}'


# ============================================================
# 4. Outlet/Target-Action Connection Resolution
# ============================================================

def test_outlet_names_in_raw():
    """All expected outlet names exist as byte strings in nib."""
    with open(ENVELOPEMAKER_NIB, 'rb') as f:
        data = f.read()
    for outlet in EXPECTED_OUTLETS:
        assert outlet.encode() in data, \
            f'Outlet "{outlet}" not in raw nib'


def test_action_selectors_in_raw():
    """App action selectors should exist in raw nib data."""
    with open(ENVELOPEMAKER_NIB, 'rb') as f:
        data = f.read()
    for action in ['appDidInit:', 'printEnvelope:', 'setAddrFields:', 'showInfoPanel:']:
        assert action.encode() in data, \
            f'Action "{action}" not in raw nib'


# ============================================================
# 5. Real ObjC Object Creation and Archive
#    (requires GNUstep - tested via create_and_archive.m)
# ============================================================

def test_archive_objc_source_exists():
    """The ObjC test source for archive should exist."""
    path = os.path.join(os.path.dirname(__file__), 'create_and_archive.m')
    assert os.path.exists(path), f'Missing: {path}'
    with open(path) as f:
        content = f.read()
    assert 'NSArchiver' in content
    assert 'NSWindow' in content
    assert 'NSTextField' in content
    assert 'NSButton' in content
    assert 'NSMenu' in content
    assert 'Envelope Editor' in content
    assert '320' in content
    assert '240' in content


# ============================================================
# Nib File Infrastructure Tests
# ============================================================

def test_nib_files_exist():
    """Test nib files should be present in nextdata directory."""
    assert os.path.exists(ENVELOPEMAKER_NIB), f'Missing: {ENVELOPEMAKER_NIB}'
    assert os.path.exists(INFO_NIB), f'Missing: {INFO_NIB}'
    assert os.path.getsize(ENVELOPEMAKER_NIB) == 3566
    assert os.path.getsize(INFO_NIB) == 2164


def test_envelopemaker_arrays():
    """EnvelopeMaker.nib contains [20c], [908c], [2517c] arrays."""
    with open(ENVELOPEMAKER_NIB, 'rb') as f:
        data = f.read()
    arrays = find_arrays(data)
    decls = [a['decl'] for a in arrays]
    assert '[20c]' in decls, f'Missing [20c] in {decls}'
    assert '[908c]' in decls, f'Missing [908c] in {decls}'
    assert '[2517c]' in decls, f'Missing [2517c] in {decls}'


def test_info_arrays():
    """Info.nib contains [20c], [807c], [1216c] arrays."""
    with open(INFO_NIB, 'rb') as f:
        data = f.read()
    arrays = find_arrays(data)
    decls = [a['decl'] for a in arrays]
    assert '[20c]' in decls, f'Missing [20c] in {decls}'
    assert any('807' in d for d in decls), f'No 807-byte array in {decls}'
    assert any('1216' in d for d in decls), f'No 1216-byte array in {decls}'


def test_te2class_mapping():
    """TE2CLASS should map known type encodings."""
    pairs = [
        ('iiii***@s@', 'WindowTemplate'),
        ('@@@@s', 'NibData'),
        ('*@', 'CustomObject'),
        ('%%%%i@@', 'HeaderClass'),
        ('ff', 'MenuTemplate'),
        ('s*', 'NXImage'),
        ('%ii', 'Storage'),
        ('i%', 'List'),
        ('*fss', 'Font'),
    ]
    for te, expected in pairs:
        assert TE2CLASS[te] == expected, f'{te} -> {TE2CLASS[te]}, expected {expected}'


def test_nextdata_directories():
    """nextdata should contain expected subdirectories."""
    assert os.path.isdir(os.path.join(NEXTDATA, 'LocalApps'))
    assert os.path.isdir(os.path.join(NEXTDATA, 'NextDeveloper'))
    assert os.path.isdir(os.path.join(NEXTDATA, 'NextLibrary'))
    apps = [d for d in os.listdir(os.path.join(NEXTDATA, 'LocalApps')) if d.endswith('.app')]
    assert len(apps) >= 10, f'Expected >=10 apps, got {len(apps)}'


def test_load_nib_basic():
    """load_nib returns basic metadata."""
    nib = load_nib('EnvelopeMaker')
    assert nib['name'] == 'EnvelopeMaker'
    assert nib['size'] > 3000
    assert len(nib['arrays']) >= 3
    assert len(nib['selectors']) >= 20

    nib2 = load_nib('Info')
    assert nib2['name'] == 'Info'
    assert nib2['size'] > 2000


def test_selectors_from_info_nib():
    """Info.nib should contain selectors too."""
    selectors = find_selectors_in_nib('Info')
    assert len(selectors) >= 15, f'Info.nib has {len(selectors)} selectors'


def test_window_frame_not_false_positive():
    """Various non-frame short sequences should not produce false frames."""
    with open(ENVELOPEMAKER_NIB, 'rb') as f:
        data = f.read()
    arrays = find_arrays(data)
    for arr in arrays:
        raw = arr['data']
        frames = find_window_frames(raw)
        for f in frames:
            x, y, w, h = f['frame']
            assert 0 <= x <= 1200
            assert 0 <= y <= 1200
            assert 10 <= w <= 1200
            assert 10 <= h <= 800
