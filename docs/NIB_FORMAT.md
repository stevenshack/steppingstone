# NeXTSTEP Nib File Format Specification & Extraction Guide

## Overview

A `.nib` file is a serialized archive of a user interface created by NeXTSTEP's Interface Builder (IB). It uses the **typedstream** serialization format — an early object graph serialization protocol that predates both NSKeyedArchiver (OS X 10.2+) and XML archives.

Nib files contain the complete description of a window's UI: its position and size, all controls (buttons, text fields, matrices, boxes), their layout frames, menu hierarchies with keyboard equivalents, outlet/target-action connections, font information, and custom class metadata.

On NeXTSTEP (m68k), nib files use **big-endian** byte order for all multibyte values.

---

## 1. Typedstream Format

### 1.1 Header

Every typedstream begins with:

```
04 0b 74 79 70 65 64 73 74 72 65 61 6d
```

| Bytes | Value | Meaning |
|-------|-------|---------|
| `04`  | 4     | Archive version (major) |
| `0b`  | 11    | Length of magic string |
| `74..6d` | "typedstream" | Magic identifier |

Followed by version/endian bytes:
```
81 03 a2
```

| Byte | Meaning |
|------|---------|
| `81 03` | Encoded integer: minor version = 3 |
| `a2` | Endianness/capabilities marker |

**Important:** The `04 0b` prefix may be absent in some typedstream variants (modern GNUstep archives omit it). NeXTSTEP nibs always include it.

### 1.2 Variable-Length Integer Encoding

Integers are encoded with a 1-byte opcode prefix indicating the byte width:

| Byte Range | Encoding | Value Range |
|-----------|----------|-------------|
| `0x01` – `0x7f` | Direct value | 1 to 127 |
| `0x81` `<byte>` | Signed 8-bit | -128 to 127 |
| `0x82` `<2 bytes big-endian>` | Signed 16-bit | -32768 to 32767 |
| `0x83` `<4 bytes big-endian>` | Signed 32-bit | -2³¹ to 2³¹-1 |
| `0x84` – `0x87` | b - 256 | -128 to -1 (one-byte negative) |
| `0x88` | Zero | 0 |
| `0xa8`, `0xac` | Recursive read | (rare extension) |

This encoding is used for ALL integer values throughout the typedstream: string lengths, versions, reference IDs, and scalar ivar values.

### 1.3 String Encoding

Strings are length-prefixed:

```
<length: variable-int> <bytes>
```

Where `length` is a variable-length unsigned integer (using the encoding from §1.2 but never negative). For lengths > 127, a tagged length format is used (see §1.4).

Examples:
- `0b 53 74 72 65 61 6d 54 61 62 6c 65` = length 11, bytes = "StreamTable"
- `05 40 40 40 40 73` = length 5, bytes = "@@@@s"

When a string encodes a class **type encoding** (like `%%%%i@@`), the characters are printable ASCII in the range `0x21`–`0x7c`.

### 1.4 Tagged Lengths

When a string length byte is `0x84`, it signals a **tagged length** where the actual length follows as a byte:

```
84 <length_byte>
```

Examples:
- `84 07` = length 7 (used for type encoding strings like `%%%%i@@`)
- `84 05` = length 5 (used for strings like `@@@@s`)

This encoding is used exclusively in the `0x94` class definition format (§2.2).

### 1.5 Value Types and Opcodes

Every value in the typedstream is introduced by a one-byte opcode:

#### 1.5.1 Direct values

| Opcode | Meaning | Followed by |
|--------|---------|-------------|
| `0x01`–`0x7f` | Small positive integer | (value = opcode) |
| `0x7d`, `0x7e`, `0x7f` | No-op / padding | (skip) |
| `0x81` | Signed byte integer | `<value: 1 byte>` |
| `0x82` | Signed short integer | `<value: 2 bytes big-endian>` |
| `0x83` | Signed 32-bit integer | `<value: 4 bytes big-endian>` |
| `0x00` | End of stream | (terminator) |

#### 1.5.2 References

| Opcode | Meaning | Followed by |
|--------|---------|-------------|
| `0x85` | Object reference | `<int: ref_id>` |
| `0x86` | Class reference | `<string: class_name> <int: ref_id>` |
| `0x92` | Object reference (alt) | `<int: ref_id>` |
| `0x93` | Continue / chain ref | `<int: ref_id>` |
| `0x95` | Object start w/ ref | `<int: ref_id>` then ivars, then `0x98`/`0x99` |
| `0x96` | Object reference (short) | `<int: ref_id>` |
| `0xa2` | Object reference (alt2) | `<int: ref_id>` |

Reference IDs can be:
- **Positive** — an index into the object table (0 = nil)
- **Negative** — special sentinels: `-124` (`0x84`) = nil/null

#### 1.5.3 Extended values (0x97)

The `0x97` opcode introduces an extended type value:

| Sub-opcode | Meaning | Followed by |
|------------|---------|-------------|
| `0x01` | nil | (nothing) |
| `0x02` | YES / true | (nothing) |
| `0x03` | NO / false | (nothing) |
| `0x04` | nil (alt) | (nothing) |
| `0x05` | float (32-bit IEEE) | `<4 bytes big-endian>` |
| `0x06` | double (64-bit IEEE) | `<8 bytes big-endian>` |
| `0x0c` | Class name | `<string>` |
| `0x0e` | Selector (SEL) | `<string>` |
| `0x14` | End of ivars marker | (nothing; internal) |
| `0x16` | Integer | `<int>` |
| `0x81` | Integer (alt encoding) | `<int>` |
| `0x82` | Short integer | `<2 bytes big-endian>` |
| `0x83` | 32-bit integer | `<4 bytes big-endian>` |
| `0x84` | Tagged string (class name reference) | `<string>` |

#### 1.5.4 Tagged values (0x84)

The `0x84` opcode introduces a **tagged value**. The byte after `0x84` is the tag indicating the value type:

| Tag | Meaning | Followed by |
|-----|---------|-------------|
| `0x01` | Integer | `<int>` |
| `0x05` | Byte array `[Nc]` | `[Nc] <N bytes>` (see §1.6) |
| `0x06` | Array (4-byte size) | `[Ntype] <N elements>` (see §1.6) |
| `0x07` | Array (2-byte size) | `[Ntype] <N elements>` (see §1.6) |
| `0x25` | String | `<string>` |
| `0x40` | Anonymous object start | `<ivars...> 0x98/0x99` |
| `0x84` | Old-style class definition | `<84|direct_len> <name_bytes> <ver_int>` (see §2.1) |
| `0x85` | Reference | `<int>` |
| `0x86` | Class reference | `<string> <int>` |

#### 1.5.5 Control opcodes

| Opcode | Meaning |
|--------|---------|
| `0x98` | End of current object (pop nesting) |
| `0x99` | End of current object (alt) |
| `0x88` | nil |
| `0x8c` | Array type name | `<string>` |
| `0x9c`, `0x9d` | nil (alt) |
| `0xa8`, `0xac` | Integer (alt) |

### 1.6 Array (`[Nc]`) Encoding

Byte arrays are encoded as:

```
84 <tag> 5b <N> <element_type> 5d <N bytes of data>
```

Where:
- `<tag>` = `05` (1-byte size prefix), `06` (4-byte), or `07` (2-byte)
- `5b` = ASCII `[`
- `<N>` = decimal number (ASCII digits)
- `<element_type>` = a single ASCII character (`c` for char/byte)
- `5d` = ASCII `]`
- `<N bytes>` = the raw data

Despite tags `06` and `07` theoretically meaning "size before declaration", in NeXTSTEP nib archives ALL variants encode the size IN the bracket declaration. Parsers should read the declaration `[Ntype]` to get the size, regardless of tag value.

Examples from actual nibs:
- `84 05 [20c]` + 20 bytes — a 20-byte char array
- `84 06 [908c]` + 908 bytes — a 908-byte char array
- `84 07 [1216c]` + 1216 bytes — a 1216-byte char array

These arrays often contain **nested typedstreams** (§3). Detection: the array data starts with `04 0b typedstream`.

---

## 2. Object Encoding (NSArchiver format)

Nib files use the **old-style NSArchiver format**, where objects are encoded sequentially with class definitions, type encoding strings, and ivar values.

### 2.1 Old-Style Class Definition (`84 84`)

The most common class definition format:

```
84 84 [84] <length> <class_name_bytes> <version_int>
```

| Byte(s) | Meaning |
|---------|---------|
| `84 84` | Class definition marker |
| `84` (optional) | When present, the length byte follows as a tagged-length (§1.4) |
| `<length>` | Length of class name (1 byte, `0x01`–`0x7f`) |
| `<bytes>` | Class name (length bytes, ASCII) |
| `<version>` | Class version integer |

The third `84` byte (when present) acts as a tag prefix for the length — it signals that the length value is encoded using the tagged-length scheme. Some archives use `84 84` directly followed by the length byte, others use `84 84 84`.

**After the class definition**, the ivar values follow. The type encoding string is NOT stored inline — the decoder must look up the type encoding from the runtime (or from a class database). This is the key difference from the `0x94` format.

### 2.2 New-Style Class Definition (`94`)

```
94 [tagged_len|<chars>] <ivar_values...>
```

| Byte(s) | Meaning |
|---------|---------|
| `94` | Class definition opcode |
| `<type_encoding>` | Type encoding string as inline chars or tagged length |
| `<ivar_values>` | Sequentially encoded ivar values (see §2.4) |

**CRITICAL:** The `0x94` format has NO version field! The type encoding string is followed DIRECTLY by the ivar values. There is no version byte between them.

The type encoding string can be:
- **Tagged length:** `84 <len> <chars>` — e.g., `84 07 %%%%i@@`
- **Direct chars:** printable ASCII bytes (`0x21`–`0x7c`) — e.g., `*@ss`

The class name itself is NOT stored in the `94` definition. The type encoding serves as the identifier. The actual class name is determined by context (the HashTable mapping in the NibData/Storage container).

### 2.3 Type Encoding Strings

Type encoding strings use the standard ObjC type encodings as documented in the official NeXTSTEP `typedstream.h` header:

| Character | Meaning |
|-----------|---------|
| `c` | `char` |
| `i` | `int` |
| `s` | `short` |
| `l` | `long` |
| `f` | `float` |
| `d` | `double` |
| `@` | `id` (object reference) |
| `%` | `NXAtom` (unique string — NOT id!) |
| `#` | `Class` |
| `:` | `SEL` (selector) |
| `*` | `char *` (C string) |
| `{...}` | Struct (e.g., `{_NSRect}`) |
| `[...]` | Array (e.g., `[10c]`) |
| `^...` | Pointer to... |
| `B` | `BOOL` |
| `I` | `unsigned int` |

**Key insight from typedstream.h:** `%` (NXAtom) and `*` (char*) are STRING types, encoded as length-prefixed C strings or as `84 84 <len> <chars>` (old-style string format). They are NOT object references.

**The `%` vs `@` distinction:** The nib format uses BOTH `%` and `@` for different purposes:
- `%` = NXAtom: a unique string value, encoded as `97 84 <len> <chars>` or `84 84 <len> <chars>`
- `@` = id: an object reference, encoded as `85 <ref>`, `92 <ref>`, `96 <ref>`, or inline object definition

When decoding `%` type ivars, if `read_val()` returns a small integer, that integer is a reference to another location in the HashTable, not the actual string value. Full resolution requires the HashTable reference map.

### 2.4 Ivar Value Encoding

Each ivar value is encoded according to its type in the type encoding string:

| ObjC Type | Typedstream Encoding | Notes |
|-----------|---------------------|-------|
| `int`, `short`, `long` | `<int>` (variable-length) | Can be `0x01-0x7f` direct or `0x81-0x83` multi-byte |
| `float` | `97 05 <4 bytes>` or `0x01-0x7f` int | Integer-valued floats may be stored as ints |
| `double` | `97 06 <8 bytes>` | |
| `id` (`@`) | `85 <ref>`, `92 <ref>`, inline object, or nil | Small ints = references when in id context |
| `NXAtom` (`%`) | `97 84 <len> <chars>` or `84 84 <len> <chars>` | String values, NOT object references |
| `SEL` (`:`) | `97 0e <string>` | |
| `char*` (`*`) | `84 84 <len> <chars>` or `<len_byte> <chars>` | C string, old-style class_def format |
| struct | inline encoded members | NSRect = 4 {f|i} |
| char array | `84 05 [Nc] <N bytes>` | |

### 2.5 Object Boundaries and Nesting

Objects nest using END markers:

- `0x98` or `0x99` — end the current object and return to parent
- `0x84 0x40` — start an anonymous object (pops on `0x98`)

**Critical rule:** `0x98` ALWAYS pops ONE level. There is NO explicit nesting marker for class definitions — the nesting is implicit from the type encoding string count and the `0x98` markers.

---

## 3. Nib File Container Structure

A nib file consists of multiple layers:

### 3.1 Outer Layer: StreamTable

The outer typedstream contains a `StreamTable` (a Foundation class similar to NSDictionary). It stores metadata and contains a `HashTable` with key-value pairs.

The outer stream uses `84 84` old-style class definitions:
```
int: 64                       ← object count (always 64 = 0x40)
class: StreamTable v1
  class: HashTable v1
    98 (end Object - no ivars)
    ... HashTable entries ...
  98 (end HashTable)
... StreamTable entries ...
98 (end StreamTable)
```

### 3.2 Inner Layer: Byte Arrays `[Nc]`

After the StreamTable, the outer stream contains one or more byte arrays `[Nc]` that hold the ACTUAL UI data:

For **EnvelopeMaker.nib** (3566 bytes):
| Array | Size | Content |
|-------|------|---------|
| `[20c]` | 20 bytes | Tiny typedstream with object ref count |
| `[908c]` | 908 bytes | HashTable with HeaderClass, Application, outlets/actions metadata |
| `[2517c]` | 2517 bytes | HashTable with ALL UI objects (windows, menus, controls) |

For **Info.nib** (2164 bytes):
| Array | Size | Content |
|-------|------|---------|
| `[20c]` | 20 bytes | Tiny HashTable entry count |
| `[807c]` | 807 bytes | HeaderClass mapping |
| `[1216c]` | 1216 bytes | All UI objects (WindowTemplate, labels, button, image) |

Each array contains a **nested typedstream** (starts with `04 0b typedstream`).

### 3.3 Nested Typedstream Object Pattern

Inside each `[Nc]` array, the nested typedstream follows this pattern:

```
int: 64                                    ← object count
class: HashTable v1
  class: Object v0                          ← hash table metadata
    (no ivars - empty)
  98 (end Object)
  85 84 = ref -124                          ← HashTable ivar data
  03 = int 3                                ← entry count
  ... key-value entries ...
98 (end HashTable)
```

After the HashTable closes, the `0x94` class definitions begin. These are the actual UI objects.

### 3.4 Complete Structure Map

```
┌─ Outer typedstream (StreamTable)
│  ├─ int 64
│  ├─ class StreamTable v1
│  │  ├─ class HashTable v1
│  │  │  ├─ class Object v0 (empty)
│  │  │  └─ ... HashTable entries (refs + ints)
│  │  └─ 98 (end HashTable)
│  └─ 98 (end StreamTable)
│  ├─ [20c] → nested typedstream (ref mapping)
│  ├─ [908c] → nested typedstream (metadata)
│  │  ├─ class HashTable v1
│  │  │  └─ ... → 94 objects: HeaderClass
│  │  └─ ...
│  └─ [2517c] → nested typedstream (UI objects)
│     ├─ class HashTable v1
│     │  ├─ class List v1 → 94 objects
│     │  └─ class NibData v0 → 94 object
│     └─ 94 objects: CustomObject, Cell, NXImage, ...
```

---

## 4. Known Nib Classes and Their Ivar Layouts

### 4.1 Internal Container Classes

These classes use `84 84` old-style class definitions. Their type encoding strings must be looked up — they are NOT stored inline.

| Class | Type Encoding | Parent | Ivars (in order) |
|-------|--------------|--------|-----------------|
| Object | (empty) | — | (no declared ivars; isa is runtime-only) |
| HashTable | `i%%` | Object | count (int), keys (id), values (id) |
| StreamTable | `i%%i%%` | Object | (wraps HashTable) |
| List | `i%` | Object | count (int), objects (id) |
| NibData | `@@@@s` | Object | objects (id), names (id), classes (id), oids (id), storage (struct) |
| Storage | `%ii` | Object | data (id), elementSize (int), elementCount (int) |
| HeaderClass | `%%%%i@@` | Object | className (NXAtom), nibName (NXAtom), outlets (NXAtom), actions (NXAtom), flags (int), obj1 (id), obj2 (id) |

### 4.2 UI Template Classes

These classes are stored as `0x94` class definitions with inline type encoding.

| Class | Type Encoding | Source (IBClasses.h ivars) |
|-------|--------------|---------------------------|
| NSWindowTemplate | `iiii***@s@` | windowRect(4i), styleMask(i), backing(i), title(*), viewClass(*), windowClass(*), windowView(@), realObject(@), extension(@), minSize(2f), flags(s), screenRect(4f) |
| NSMenuTemplate | (complex) | title(@), location(2f), view(@), menuClassName(@), supermenu(@), realObject(@), extension(@), flags... |
| NSCustomObject | `*@` | className(*), realObject(@), extension(@) |
| NSCell | `*@ss` | contents(*), image(@), font(@), objectValue(@), flags(struct), ... |
| NSActionCell | `*@ss` | (adds tag(i), target(@), action(:), controlView(@)) |
| NSButtonCell | (complex) | (adds altContents, altImage, keyEquivalent, ...) |
| NSTextFieldCell | (complex) | (adds backgroundColor, textColor, bezelStyle, placeholder) |
| NSView | (struct) | frame, bounds, superview, subviews, window, flags... |
| NSControl | `*@ss@` | tag(i), cell(@), ignoresMultiClick(B) |
| NSTextField | `@@:` | delegate(@), errorAction(:), textObj(@) |
| NSFont | `*fss` | fontName(*), size(f), flags(s), flags(s) |
| NXImage | `s*` | size(s), name(*) |
| Box | `@@` | cell(@), contentView(@) |

### 4.3 HeaderClass Structure

The HeaderClass is the metadata container for the File's Owner object. It stores:

```
Ivar 1 (%): className (NXAtom)           → "Application"
Ivar 2 (%): nibName (NXAtom)             → ref -124 (nil) or appnib name
Ivar 3 (%): outlets (NXAtom)             → count as int, then ASCII bytes of outlet names
Ivar 4 (%): actions (NXAtom)             → selector names
Ivar 5 (i): flags (int)
Ivar 6 (@): obj1 (id)
Ivar 7 (@): obj2 (id)
```

The outlet names (fromField1, fromField2, etc.) and actions (appDidInit:, printEnvelope:, etc.) are stored as consecutive ASCII bytes after the count. The `%` ivars 3-4 encode length-prefixed strings as (int_length, int_byte1, int_byte2, ...).

### 4.4 Classes Found in Nibs

| Class | Type Encoding | Description |
|-------|--------------|-------------|
| `HashTable` | `i%%` | Foundation hash table (count, keys, values) |
| `List` | `i%` | Ordered list (count, objects) |
| `NibData` | `@@@@s` | Nib container (objects, names, classes, oids, storage) |
| `Storage` | `%ii` | Raw data storage (data, elementSize, elementCount) |
| `HeaderClass` | `%%%%i@@` | Custom class metadata |
| `NSCustomObject` | `*@` | Placeholder for File's Owner etc. |
| `NSWindowTemplate` | `iiii***@s@` | Window placeholder with frame, title, style |
| `NSMenuTemplate` | `ff` | Menu structure (complex, stored as raw data) |
| `NSTextField` | `@@:` | Text input field |
| `NSButton` | (none added) | Push button (inherits from NSControl) |
| `NSBox` | `@@` | Group box |
| `NSMatrix` | `@` | Control matrix |
| `NSFont` | `*fss` | Font descriptor (name, size, flags) |
| `NXImage` | `s*` | Image reference (size, name) |
| `View` | struct | Base view class |
| `Control` | `*@ss@` | Control (view + cell) |
| `Cell` | `*@ss` | Base cell class |
| `ActionCell` | `*@ss` | Action-capable cell |
| `ButtonCell` | (complex) | Button cell with key equivalents |
| `MenuCell` | (complex) | Menu item cell |
| `Font` | `*fss` | Font descriptor |
| `NXImage` | `s*` | Image |

---

## 5. How to Parse a Nib File (Step by Step)

### Step 1: Read the outer typedstream

1. Skip the header (`04 0b typedstream 81 03 a2`)
2. The first value is `int: 64` (always)
3. Read through `StreamTable`/`HashTable`/`Object` class definitions
4. Track nesting via `0x98`/`0x99` markers

### Step 2: Extract all `[Nc]` arrays

Scan the outer typedstream for all `84 05`, `84 06`, or `84 07` byte sequences followed by `[Nc]` bracket declarations:

```
84 <tag> [0-9]+[a-z]
```

Extract each array's declaration and data. The arrays contain the real UI objects.

### Step 3: For each array, check for nested typedstream

If the array data starts with `04 0b typedstream`, it contains a nested typedstream. Parse it recursively.

### Step 4: Skip container classes to find 94 objects

Within each nested typedstream:
1. Classes defined with `84 84` (HashTable, Object, List, NibData, Storage) are INTERNAL CONTAINERS — skip them
2. Search for `0x94` bytes using a direct byte scan
3. For each `0x94`, advance past the opcode and read the type encoding

### Step 5: Decode 94 class definitions

For each `0x94` class definition:

```python
pe = r.r1()
if pe == 0x84:
    l = r.r1()
    type_enc = r.rn(l).decode('latin-1')
elif 0x21 <= pe <= 0x7c:
    # Read printable chars until non-printable
    chars = [chr(pe)]
    while r.o < len(r.d) and 0x21 <= r.d[r.o] <= 0x7c:
        chars.append(chr(r.d[r.o])); r.adv()
    type_enc = ''.join(chars)
else:
    return (None, [])  # Not a valid 94 class_def
```

### Step 6: Decode ivars by type encoding

For each character in the type encoding string, read one ivar value:

| Type | Decoder |
|------|---------|
| `@` | `read_val()` — returns ('r', ref), ('obj', {...}), ('n', nil), etc. |
| `%` | `read_val()` — returns string or ref to string in HashTable |
| `i` `c` `s` `l` `I` `B` | `read_val()` — returns ('i', int) or small int type |
| `f` `d` | `read_val()` — returns float. Check for `97 05` prefix. If int returned, convert to float. |
| `*` | `read_cstr()` — handles `84 84 <len> <chars>` or direct `<len> <chars>` |
| `:` | `r.rs()` — selector string |
| `#` | `r.rs()` — class name string |

### Step 7: Extract all strings and selectors (flat scan)

Use regex and byte-pattern matching on the raw data to extract ALL strings and selectors:

```python
# Objective-C selectors (method names ending with ':')
for m in re.finditer(b'[A-Za-z_][A-Za-z0-9_]+:', data):
    selectors.add(m.group().decode('ascii'))

# Strings from 0x97 extended values
# 0x97 0x0c <len> <chars> = class name
# 0x97 0x0e <len> <chars> = selector
# 0x97 0x84 <len> <chars> = tagged string
i = 0
while i < len(data) - 3:
    if data[i] == 0x97 and data[i+1] in (0x0c, 0x0e, 0x84):
        l = data[i+2]
        if 0 < l < 60:
            s = data[i+3:i+3+l].decode('latin-1')
            # add s to strings or selectors based on subtype
        i += 3; continue
    i += 1
```

### Step 8: Build the object graph

The 94-objects form the UI object tree:
1. NibData → Storage (container hierarchy)
2. CustomObject → EnvelopeApp (File's Owner)
3. Cells with string values ("Info", "Envelope Maker")
4. Font objects (Helvetica, sizes)
5. NXImage references ("envelope")

References in `@` ivars (like `('r', -122)`) point to other objects in the graph:
- `-124` (0x84) = nil
- `-122` (0x86) = the NibData container itself (self-reference)
- `-1` = File's Owner proxy
- `-2` = First Responder proxy
- Positive values = index into the object list

### Step 9: Generate Gorm-compatible output

The `.gmodel` format is a GNUstep property list with objects keyed as `"Object    N"`:

```
{
"Object    1" = { elements = (...); isa = "NSMutableArray"; };
"Object    2" = { className = "EnvelopeApp"; isa = "IMCustomObject"; realObject = nil; };
"Object    3" = { frame = "{x = 0; y = 0; width = 320; height = 240}"; isa = "NSWindow"; title = "Envelope Editor"; };
...
}
```

---

## 6. Reference Data

### 6.1 EnvelopeMaker.nib Objects

| # | Type Enc | Class | Key Data |
|---|----------|-------|----------|
| 1 | `%%%%i@@` | HeaderClass | "Application", outlet/action metadata |
| 2 | `@@@@s` | NibData | Container with Storage sub-object |
| 3 | `*@` | CustomObject | "EnvelopeApp", ref to container |
| 4 | `*@ss` | Cell | "Info", Helvetica 12pt |
| 5 | `s*` | NXImage | NXreturnSign, Box reference |
| — | — | (implicit) | **Window:** "Envelope Editor", 320×240 |
| — | — | (implicit) | **Fields:** fromField1-4, toField1-5 |
| — | — | (implicit) | **Buttons:** Set → printEnvelope:, Print → printEnvelope: |
| — | — | (implicit) | **Menus:** App (Hide/Quit), Edit (Cut/Copy/Paste/SelectAll), Window (Miniaturize/Close) |
| — | — | (implicit) | **View:** EnvelopeView (custom NSView subclass) |

### 6.2 Info.nib Objects

| # | Type Enc | Class | Key Data |
|---|----------|-------|----------|
| 1 | `%%%%i@@` | HeaderClass | "Application", outlet/action metadata |
| 2 | `@@@@s` | NibData | Container with Storage sub-object |
| 3 | `*@` | CustomObject | "EnvelopeApp" |
| 4 | `ffff` | NSRect | Window frame (1, 83, 2, 7 — actually int values from struct data) |
| 5 | `*@ss` | Cell | "Envelope Maker", Helvetica 18pt |
| 6 | `s*` | NXImage | "envelope" (correctly resolved) |

### 6.3 Known Selectors

All 31 selectors from EnvelopeMaker.nib:
`alignSelCenter:`, `alignSelLeft:`, `alignSelRight:`, `appDidInit:`, `arrangeInFront:`, `checkSpelling:`, `copy:`, `copyFont:`, `copyRuler:`, `cut:`, `delete:`, `hide:`, `orderFrontColorPanel:`, `paste:`, `pasteFont:`, `pasteRuler:`, `performClick:`, `performClose:`, `performMiniaturize:`, `printEnvelope:`, `runPageLayout:`, `selectAll:`, `setAddrFields:`, `showGuessPanel:`, `showInfoPanel:`, `subscript:`, `superscript:`, `terminate:`, `toggleRuler:`, `underline:`, `unscript:`

### 6.4 Proxy Object Reference IDs

| ID | Object |
|----|--------|
| -124 (0x84) | nil |
| -122 (0x86) | NibData container (self) |
| -1 | File's Owner |
| -2 | First Responder |
| -3 | NSApplication |

---

## 7. Pipeline Tools Reference

The `nextthunk` project provides these tools for nib extraction:

| Tool | Function | Status |
|------|----------|--------|
| `nib_complete.py` | Full extractor: all 94-objects + flat atom scan | Working |
| `nib_extract.py` | Flat atom scanner (strings, selectors, classes, arrays) | Working |
| `nib_parser.py` | Type-encoding-driven ivar decoder | Working |
| `nib2gmodel.py` | Gorm-compatible .gmodel generator (55+ objects) | Working |
| `nib2ui.py` | ObjC UI setup code generator | Working |
| `gen_runtime_gmodel.py` | GCC-compat ObjC runtime config | Working |

**Output files:**

| File | Format | Purpose |
|------|--------|---------|
| `*.gmodel` | Gorm ASCII property list | Editable in Gorm Interface Builder |
| `*_runtime_gmodel.m` | ObjC source | Compiled into app, creates UI at startup |
| `*.dump.json` | JSON | Complete extracted data for analysis |
| `*.complete.json` | JSON | Full object tree with resolved references |

**Key implementation insights discovered through reverse engineering:**

1. `%` (NXAtom) and `@` (id) are DISTINCT types — `%` is a string value, `@` is an object reference
2. `*` (char*) values use `84 84 <len> <chars>` encoding (same byte pattern as old-style class_def, but NO version byte)
3. `0x94` class_defs have NO version field — the type encoding is followed DIRECTLY by ivar values
4. `0x84 0x84` can mean EITHER a class_def (when followed by length+name+version) OR a string (when followed by length+chars) — context determines which
5. The old NSArchiver format used in nibs is DIFFERENT from the GNUstep archive format (different header prefix, different type tag system)
6. GCC does NOT support modern ObjC literals (`@{}`, `@[]`, `@()`) — only Clang does
7. The HashTable's `i%%` encoding stores: count (int), keys (NXAtom reference), values (object reference)
