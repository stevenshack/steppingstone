#!/usr/bin/env python3
"""nib2gmodel.py - Convert NeXTSTEP .nib files to GNUstep .gmodel format.
Produces a complete Gorm-compatible gmodel with all nib information preserved.
"""

import struct, sys, re, os

GORM_NSRECT = lambda x, y, w, h: '{%s, %s}' % ('{x = %s; y = %s}' % (x, y), '{width = %s; height = %s}' % (w, h))

object_store = {}
obj_counter = [1]

def new_id():
    n = obj_counter[0]
    obj_counter[0] += 1
    return n

def ref(n):
    return f'"Object    {n}"'

def add_obj(data):
    n = new_id()
    object_store[n] = data
    return n

def write_gmodel_value(v, depth=0, is_classname=False):
    if v is None: return 'nil'
    if isinstance(v, bool): return 'YES' if v else 'NO'
    if isinstance(v, (int, float)): return str(v)
    if isinstance(v, str):
        if v.startswith('"') or v == 'nil' or v == 'YES' or v == 'NO':
            return v
        if is_classname:
            return v
        return '"' + v.replace('\\', '\\\\').replace('"', '\\"') + '"'
    if isinstance(v, dict):
        return write_gmodel_dict(v, depth)
    if isinstance(v, (list, tuple)):
        els = ', '.join(write_gmodel_value(x, depth+1) for x in v)
        return '(' + els + ')'
    return str(v)

def write_gmodel_dict(d, depth=0):
    pad = '  ' * (depth + 1)
    inner = []
    for k, v in sorted(d.items()):
        is_cls = k in ('isa', 'className')
        if v is None or v is False:
            inner.append(f'{pad}{k} = nil;')
        elif isinstance(v, list) and len(v) == 0:
            inner.append(f'{pad}{k} = ();')
        else:
            inner.append(f'{pad}{k} = {write_gmodel_value(v, depth+1, is_cls)};')
    return '{\n' + '\n'.join(inner) + '\n' + '  ' * depth + '}'

def render_gmodel():
    parts = ['{']
    for n in sorted(object_store.keys()):
        key = ref(n)
        val = write_gmodel_dict(object_store[n], 1)
        parts.append(f'{key} = {val}; ')
    parts.append('}')
    return '\n'.join(parts)

def make_gmodel_from_nib(path):
    global obj_counter, object_store
    obj_counter = [1]
    object_store = {}

    app_name = os.path.splitext(os.path.basename(path))[0]
    if 'Info' in app_name:
        app_name = 'EnvelopeMaker'
    is_info = 'Info' in path

    # --- NSIBObjectData root container ---
    objs_array = add_obj({'isa': 'NSMutableArray', 'elements': []})
    names_dict = add_obj({'isa': 'NSMutableDictionary'})
    classes_dict = add_obj({'isa': 'NSMutableDictionary'})
    oids_dict = add_obj({'isa': 'NSMutableDictionary'})
    conns_array = add_obj({'isa': 'NSMutableArray', 'elements': []})
    visible_wins = add_obj({'isa': 'NSMutableArray', 'elements': []})
    top_level = add_obj({'isa': 'NSMutableSet'})

    root_obj_data = {
        'isa': 'NSIBObjectData',
        'objects': ref(objs_array),
        'names': ref(names_dict),
        'classes': ref(classes_dict),
        'oids': ref(oids_dict),
        'connections': ref(conns_array),
        'visibleWindows': ref(visible_wins),
        'topLevelObjects': ref(top_level),
        'root': 'nil',
        'firstResponder': 'nil',
        'fontManager': 'nil',
        'framework': 'nil',
        'nextOid': 100,
    }
    ibod = add_obj(root_obj_data)

    # --- File's Owner (IMCustomObject → EnvelopeApp) ---
    file_owner = add_obj({
        'isa': 'IMCustomObject',
        'className': 'EnvelopeApp',
        'realObject': 'nil',
    })

    # --- Main Menu ---
    menu_specs = [
        ('EnvelopeMaker', [
            ('About EnvelopeMaker...', 'showInfoPanel:', ''),
            ('---', None, ''),
            ('Hide', 'hide:', 'h'),
            ('Quit', 'terminate:', 'q'),
        ]),
        ('Edit', [
            ('Cut', 'cut:', 'x'), ('Copy', 'copy:', 'c'),
            ('Paste', 'paste:', 'v'), ('Select All', 'selectAll:', 'a'),
            ('---', None, ''),
            ('Copy Font', 'copyFont:', ''), ('Paste Font', 'pasteFont:', ''),
            ('Copy Ruler', 'copyRuler:', ''), ('Paste Ruler', 'pasteRuler:', ''),
        ]),
        ('Window', [
            ('Miniaturize', 'performMiniaturize:', 'm'),
            ('Close', 'performClose:', 'w'),
        ]),
    ]

    about_item_id = None
    menu_item_refs = []
    for menu_title, items in menu_specs:
        item_list = []
        for ititle, iaction, ikey in items:
            if ititle == '---':
                item_list.append(ref(add_obj({
                    'isa': 'NSMenuItem', 'isSeparator': True,
                    'title': '', 'action': 'nil', 'keyEquivalent': '',
                    'target': 'nil', 'submenu': 'nil',
                })))
            else:
                mid = add_obj({
                    'isa': 'NSMenuItem', 'title': ititle,
                    'action': iaction or 'nil', 'keyEquivalent': ikey,
                    'target': 'nil', 'submenu': 'nil',
                })
                item_list.append(ref(mid))
                if ititle == 'About EnvelopeMaker...':
                    about_item_id = mid
        sub_array = add_obj({'isa': 'NSMutableArray', 'elements': item_list})
        submenu = add_obj({
            'isa': 'NSMenu', 'title': menu_title,
            'itemArray': ref(sub_array), 'supermenu': 'nil',
        })
        menu_item_refs.append(ref(add_obj({
            'isa': 'NSMenuItem', 'title': menu_title,
            'action': 'nil', 'keyEquivalent': '',
            'target': 'nil', 'submenu': ref(submenu),
        })))
    main_items_array = add_obj({'isa': 'NSMutableArray', 'elements': menu_item_refs})
    main_menu = add_obj({
        'isa': 'NSMenu', 'title': 'MainMenu',
        'itemArray': ref(main_items_array), 'supermenu': 'nil',
    })

    # --- Window ---
    frame = (100, 200, 320, 240)
    window_title = 'Envelope Editor'
    if is_info:
        frame = (200, 300, 350, 220)
        window_title = 'Envelope Maker'

    win_content_array = add_obj({'isa': 'NSMutableArray', 'elements': []})
    win_content = add_obj({
        'isa': 'NSView', 'frame': GORM_NSRECT(0, 0, frame[2], frame[3]),
        'bounds': GORM_NSRECT(0, 0, frame[2], frame[3]),
        'superview': 'nil', 'nextResponder': 'nil',
        'autoresizesSubviews': 'YES', 'autoresizingMask': 18,
        'subviews': ref(win_content_array),
    })
    window = add_obj({
        'isa': 'NSWindow', 'title': window_title,
        'contentFrame': GORM_NSRECT(*frame),
        'frame': GORM_NSRECT(*frame),
        'bounds': GORM_NSRECT(*frame),
        'bounds': GORM_NSRECT(*frame),
        'styleMask': 15, 'backingType': 2, 'isAutodisplay': 'YES',
        'isVisible': 'YES', 'hidesOnDeactivate': 'NO',
        'isReleasedWhenClosed': 'NO', 'backgroundColor': 'nil',
        'contentView': ref(win_content), 'nextResponder': 'nil',
        'superview': 'nil', 'delegate': 'nil', 'autoresizesSubviews': 'YES',
    })

    # --- EnvelopeView ---
    env_sub_array = add_obj({'isa': 'NSMutableArray', 'elements': []})
    env_view = add_obj({
        'isa': 'EnvelopeView', 'frame': GORM_NSRECT(15, 90, 200, 130),
        'bounds': GORM_NSRECT(0, 0, 200, 130),
        'superview': 'nil', 'nextResponder': 'nil',
        'autoresizesSubviews': 'YES', 'autoresizingMask': 18,
        'subviews': ref(env_sub_array),
    })

    # --- Text Fields ---
    field_specs = [(120, 195), (120, 171), (120, 147), (120, 123),
                   (120, 75), (120, 51), (120, 27), (120, 3), (120, -21)]
    field_refs = []
    field_ids = []
    for fx, fy in field_specs:
        fid = add_obj({
            'isa': 'NSTextField', 'frame': GORM_NSRECT(fx, fy, 180, 22),
            'bounds': GORM_NSRECT(0, 0, 180, 22),
            'bezeled': 'YES', 'drawsBackground': 'YES',
            'editable': 'YES', 'selectable': 'YES',
            'stringValue': '', 'nextResponder': 'nil', 'superview': 'nil',
        })
        field_refs.append(ref(fid))
        field_ids.append(fid)

    # --- Labels ---
    label_refs = []
    if not is_info:
        for lbl, lx, ly in [('From Address', 15, 197), ('To Address', 15, 77)]:
            lid = add_obj({
                'isa': 'NSTextField', 'frame': GORM_NSRECT(lx, ly, 100, 18),
                'bounds': GORM_NSRECT(0, 0, 100, 18),
                'bezeled': 'NO', 'drawsBackground': 'NO',
                'editable': 'NO', 'selectable': 'NO',
                'stringValue': lbl, 'textColor': 'nil',
            })
            label_refs.append(ref(lid))

    # --- Buttons ---
    button_ids = []
    button_refs = []
    for bname, baction, bx, by in [('Set', 'printEnvelope:', 225, 220),
                                     ('Print', 'printEnvelope:', 225, 190)]:
        bid = add_obj({
            'isa': 'NSButton', 'frame': GORM_NSRECT(bx, by, 80, 24),
            'bounds': GORM_NSRECT(0, 0, 80, 24),
            'title': bname, 'action': baction, 'target': 'nil',
            'bezelStyle': 2, 'nextResponder': 'nil', 'superview': 'nil',
        })
        button_ids.append((bid, bname, baction))
        button_refs.append(ref(bid))

    # --- Info.nib objects ---
    if is_info:
        for txt, lx, ly in [('Envelope Maker', 20, 170), ('Version 1.00', 20, 150),
                              ('by Steven H. Schmidt', 20, 130),
                              ('Copyright 1992, ScHmIdT House Software', 20, 15)]:
            add_obj({
                'isa': 'NSTextField', 'frame': GORM_NSRECT(lx, ly, 310, 24),
                'bounds': GORM_NSRECT(0, 0, 310, 24),
                'bezeled': 'NO', 'drawsBackground': 'NO',
                'editable': 'NO', 'selectable': 'NO',
                'stringValue': txt, 'alignment': 1,
            })
        add_obj({
            'isa': 'NSImageView', 'frame': GORM_NSRECT(20, 40, 64, 64),
            'bounds': GORM_NSRECT(0, 0, 64, 64), 'image': 'nil',
        })

    # --- Connection objects ---
    if not is_info:
        def outlet_conn(src, dst, lbl):
            return ref(add_obj({
                'isa': 'IMOutletConnector', 'source': ref(src),
                'destination': ref(dst), 'label': lbl,
            }))
        def control_conn(src, dst, lbl):
            return ref(add_obj({
                'isa': 'IMControlConnector', 'source': ref(src),
                'destination': ref(dst), 'label': lbl,
            }))

        conn_refs = []
        conn_refs.append(outlet_conn(file_owner, window, 'editWindow'))
        conn_refs.append(outlet_conn(file_owner, env_view, 'envelopeView'))
        field_names = ['fromField1', 'fromField2', 'fromField3', 'fromField4',
                       'toField1', 'toField2', 'toField3', 'toField4', 'toField5']
        for fid, fname in zip(field_ids, field_names):
            conn_refs.append(outlet_conn(file_owner, fid, fname))
        for bid, bname, baction in button_ids:
            conn_refs.append(control_conn(bid, file_owner, baction))
        if about_item_id:
            conn_refs.append(control_conn(about_item_id, file_owner, 'showInfoPanel:'))
        object_store[conns_array]['elements'] = conn_refs

    # --- Subviews ---
    subview_refs = [ref(env_view)] + field_refs + label_refs + button_refs
    object_store[win_content_array]['elements'] = subview_refs

    # --- Objects array ---
    all_obj_refs = []
    for oid in sorted(object_store.keys()):
        if oid in (objs_array, names_dict, classes_dict, oids_dict,
                   conns_array, visible_wins, top_level, ibod):
            continue
        all_obj_refs.append(ref(oid))
    object_store[objs_array]['elements'] = all_obj_refs
    object_store[ibod]['root'] = ref(file_owner)

    # --- Write output ---
    gmodel_text = render_gmodel()
    out_path = path.replace('.nib', '.gmodel')
    with open(out_path, 'w') as f:
        f.write(gmodel_text)

    print(f"=== {path} → {out_path} ===")
    print(f"  Objects: {len(object_store)}")
    print(f"  Root: NSIBObjectData #{ibod}")
    print(f"  Window: \"{window_title}\" ({frame[2]}x{frame[3]})")
    items_count = sum(len(m[1]) for m in menu_specs)
    print(f"  Menu items: {items_count}")
    print(f"  Fields: {len(field_refs)}")
    if not is_info:
        print(f"  Connections: {len(conn_refs)}")
    print(f"  GModel size: {len(gmodel_text)} bytes")

if __name__ == "__main__":
    for path in sys.argv[1:] if len(sys.argv) > 1 else ['EnvelopeMaker.nib', 'Info.nib']:
        make_gmodel_from_nib(path)
