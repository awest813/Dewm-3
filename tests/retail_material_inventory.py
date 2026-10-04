"""Inventory explicit material programs and compiled-map references in local PK4s.

Read-only; emits derived names/counts, never material, map or shader source.
Dynamic models, skins and engine-selected programs are outside this inventory.
"""
import argparse
import json
from pathlib import Path
import re
import zipfile


LEXER = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|[{}]|[^\s{}]+', re.S)


def tokens(source):
    return [match.group() for match in LEXER.finditer(source)
            if not match.group().startswith(('//', '/*'))]


def declarations(source):
    """Yield outer declaration names and bodies, respecting strings/comments."""
    words = tokens(source)
    depth = 0
    name = None
    start = 0
    for i, word in enumerate(words):
        if word == '{':
            if depth == 0:
                name = words[i - 1].strip('"') if i else ''
                start = i + 1
            depth += 1
        elif word == '}':
            depth -= 1
            if depth < 0:
                raise ValueError('Unbalanced declaration braces')
            if depth == 0:
                yield name, words[start:i]
    if depth:
        raise ValueError('Unclosed declaration')


def inventory(base):
    archives = sorted(base.glob('pak*.pk4'), key=lambda p: p.name.casefold())
    if not archives:
        raise ValueError(f'No pak*.pk4 files in {base}')
    # Later archives override earlier files, as in the engine search path.
    owners = {}
    for archive in archives:
        with zipfile.ZipFile(archive) as package:
            for name in package.namelist():
                if name.lower().endswith(('.mtr', '.proc')):
                    owners[name.lower()] = (archive, name)
    materials = {}
    map_refs = {}
    # Material replacement can remove a previously programmed declaration.
    for key in sorted(owners):
        if not key.endswith('.mtr'):
            continue
        archive, name = owners[key]
        with zipfile.ZipFile(archive) as package:
            source = package.read(name).decode('latin1')
        for material, body in declarations(source):
            programs = sorted({body[i + 1].strip('"') for i, word in enumerate(body[:-1])
                               if word.lower() in ('program', 'vertexprogram', 'fragmentprogram')})
            materials[material.lower()] = {'source': key, 'programs': programs}
    materials = {name: data for name, data in materials.items() if data['programs']}
    for key in sorted(owners):
        if not key.endswith('.proc'):
            continue
        archive, name = owners[key]
        with zipfile.ZipFile(archive) as package:
            words = tokens(package.read(name).decode('latin1'))
        references = {word.strip('"').lower() for word in words} & materials.keys()
        for material in sorted(references):
            map_refs.setdefault(material, []).append(key)
    return {
        'scope': 'Explicit material programs and compiled-map references; excludes dynamic models, skins and engine-selected programs.',
        'archives': [archive.name for archive in archives],
        'programs': sorted({program for data in materials.values() for program in data['programs']}),
        'materials': materials,
        'compiled_map_references': map_refs,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', type=Path, help='Local game base directory containing PK4 archives')
    parser.add_argument('--output', type=Path, help='Write derived inventory JSON to this file')
    args = parser.parse_args()
    try:
        result = inventory(args.base)
        encoded = json.dumps(result, indent=2)
        if args.output:
            args.output.write_text(encoded + '\n', encoding='utf-8')
            print(f"Inventoried {len(result['materials'])} programmed materials, {len(result['programs'])} programs, "
                  f"{len(result['compiled_map_references'])} materials referenced in compiled maps.")
        else:
            print(encoded)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        parser.exit(1, f'Inventory failed: {error}\n')


if __name__ == '__main__':
    main()
