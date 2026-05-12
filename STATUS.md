# Pipeline Status

## What Works

### Pipeline Flow (`./pipeline.sh path/to/binary`)
1. **Architecture detection** — auto-detects i386 LE vs m68k BE Mach-O
2. **ObjC metadata dump** — method names + IMP addresses from `__OBJC` segment
3. **Ghidra batch decompilation** — decompiles all methods via headless Ghidra
4. **Class layout extraction** — class hierarchy, ivar names/types/offsets from `__class`
5. **Source generation** — ObjC `.m`/`.h` with class routing, ivar names, selector resolution
6. **Stubs generation** — extern symbols, `objc_msgSend` bridge (`__builtin_apply`), `main()`, menu bar
7. **Nib → gmodel conversion** — two types:
   - **Preservation gmodel** (`*_nib.gmodel`): raw nib bytes + extracted metadata strings (round-trippable)
   - **Runtime gmodel** (`AppName.gmodel`): UI config dict (window size, field names/labels/positions)
8. **App bundle creation** — `.app` directory with binary, Info.plist, gmodels

### Binary Decompilation
- 16/16 methods decompiled and class-routed (EnvelopeApp, EnvelopeView)
- Ivar offsets replaced with named access (`self->fromField1`)
- `objc_msgSend` forwards via `objc_msg_lookup` + `__builtin_apply`
- Zero compiler errors (with `-fpermissive`)

### Nib Round-Trip
- `nib → preservation gmodel → nib → preservation gmodel` = **bit-identical**
- This works because `nib2gmodel.m` stores the raw nib bytes as `NSData` without ANY parsing.
- `gmodel2nib.m` writes the raw bytes back.
- **No typedstream understanding is involved in the round trip.**

## Current Nib Parsing (`extract_nib.py`)

### What the typedstream parser DOES extract correctly
All **typed atoms** from the outer and nested ([908c]) typedstreams:
- **Class definitions**: `HashTable`, `Object`, `NibData`, `Storage`, `File's Owner`, `CustomObject`, `EnvelopeApp`, `MainMenu`, `MenuTemplate`, `WindowTemplate`, `Matrix`, `Control`, `View`, `Responder`, `Button`, `Text/TextField`, `MenuCell`, `ButtonCell`, `ActionCell`, `Cell`, etc.
- **Selectors**: `appDidInit:`, `printEnvelope:`, `setAddrFields:`, `showInfoPanel:`, `cut:`, `copy:`, `paste:`, `selectAll:`, etc.
- **Object references** and **nesting structure** (504 atoms for EnvelopeMaker.nib, 304 for Info.nib)

### What the parser DOES NOT extract
- **Window frames** (position, size, title) — stored as raw C struct shorts inside `[908c]` byte array, not as typedstream floats. On m68k NeXTSTEP, `NXRect` coordinates are stored as **short integers** (16-bit big-endian), not IEEE 754 floats. The typedstream parser only sees these as opaque raw data.
- **Text field frames** — same issue, stored as short ints inside the raw struct data.
- **Menu item hierarchy** — `MenuTemplate` class data is in the raw structs, not decoded.
- **Outlet connections** — `NSNibOutletConnector` objects exist in the typedstream but their target/source references aren't resolved into a usable form.
- **Window title** ("Envelope Editor") — stored inside the WindowTemplate struct data.
- **Button labels, default values, colors, fonts** — all inside raw struct data.

### Why the Runtime UI is Wrong
`build_runtime_gmodel.m` only reads **extracted strings** (field names/labels) from the preservation gmodel's metadata. It does NOT use the typedstream parser. It makes up generic positions:
```objc
float y = windowH - 40;
for (i = 0; i < [fieldSpecs count]; i++) {
    // Uses guessed y position, not nib frame data
}
```

The runtime gmodel has **no knowledge** of:
- The window's actual size (320×240 in nib, guessed at 400×something)
- The window's title ("Envelope Editor" in nib, guessed as "Envelopemaker")
- Text field positions (nib-specific shorts, guessed as evenly spaced)
- The menu structure (replaced with hardcoded App/Edit/Window menus)
- The Print button and its connection to `printEnvelope:`
- The Show Info Panel button/menu item

## What's Needed for Full Nib Conversion
Full nib conversion requires:
1. **Parse the WindowTemplate struct** from the `[908c]` byte array — extract frame (4 shorts: x,y,w,h), title (C string), styleMask
2. **Parse the MenuTemplate struct** — menu items with their titles, key equivalents, actions, submenus
3. **Parse Text/Button/Control structs** — frames, string values, action selectors
4. **Resolve outlet/target-action connections** — link `fromField1` outlet to its NSTextField, link `printEnvelope:` action to the Button
5. **Create real ObjC objects** (NSWindow, NSTextField, NSButton, NSMenu, NSMenuItem) with the correct frames and properties
6. **Archive via NSArchiver** into the runtime gmodel

The struct layouts for NeXTSTEP classes are documented in the OPENSTEP SDK headers but are class-specific. Each class has a known struct layout for its "nib template" data — WindowTemplate is ~908 bytes, MenuTemplate is ~2517 bytes, etc.
