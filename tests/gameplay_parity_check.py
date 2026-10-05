"""Compare testUsercmd simulation checkpoints from native and web console logs.

Console dumps wrap long lines mid-word; DOM console text does not. Neither
format is a simulation oracle: this compares two actual engine runs and checks
that their fixed-tick input advanced game time and exercised physical movement.
No game assets are copied into this tool.
"""
import argparse
from pathlib import Path
import re


def checkpoints(path):
    text = Path(path).read_text(encoding='utf-8', errors='replace')
    if 'testUsercmd: stopped' in text or 'testUsercmd: end the cinematic' in text:
        raise ValueError(f'{path}: replay interrupted')
    records = []
    pending = ''
    phase = ''
    for line in text.splitlines():
        if line.startswith('PARITY_PHASE '):
            phase = line.split()[1]
        if line.startswith('USERCMD_CHECK '):
            pending = line
        elif pending:
            pending += line
        if pending and re.search(r'\bnoclip=\d+', pending):
            # Native condump may trim a space exactly at the wrap boundary.
            # Read numeric fields by their labels rather than word spacing.
            fields = dict(re.findall(r'(ticks|elapsed|origin|velocity|ground|crouch|health|clip|ammo|ready|view|noclip)=(-?\d+(?:\.\d+)?(?:,-?\d+(?:\.\d+)?){0,2})', pending))
            record = {}
            for key, value in fields.items():
                record[key] = tuple(map(float, value.split(','))) if key in ('origin', 'velocity', 'view') else int(value)
            if any(len(record[key]) != 3 for key in ('origin', 'velocity', 'view') if key in record):
                raise ValueError(f'{path}: incomplete vector evidence')
            expected = {'ticks', 'elapsed', 'origin', 'velocity', 'ground', 'crouch', 'health', 'clip', 'ammo', 'ready', 'noclip'}
            if 'view' in record:
                weapon = re.search(r'weapon=(.*?)view=', pending)
                if not weapon or not weapon[1].strip():
                    raise ValueError(f'{path}: missing weapon identity')
                record['weapon'] = weapon[1].strip()
                expected |= {'view', 'weapon'}
            if set(record) != expected:
                raise ValueError(f'{path}: malformed checkpoint {pending}')
            if record['elapsed'] != 16 * record['ticks'] or record['noclip']:
                raise ValueError(f'{path}: fixed ticks or physical collision were bypassed')
            if phase:
                record['phase'] = phase
            records.append(record)
            pending = ''
    if pending or not records:
        raise ValueError(f'{path}: incomplete or absent checkpoints')
    return records


def compare(native, web, tolerance=0.001, scenario='movement'):
    if len(native) != len(web):
        raise ValueError(f'checkpoint count differs: {len(native)} / {len(web)}')
    for index, (left, right) in enumerate(zip(native, web), 1):
        if set(left) != set(right):
            raise ValueError(f'checkpoint {index}: evidence fields differ')
        for field in left:
            if field in ('origin', 'velocity', 'view'):
                delta = max(abs(a-b) for a, b in zip(left[field], right[field]))
                if delta > tolerance:
                    raise ValueError(f'checkpoint {index} {field}: {left[field]} / {right[field]} (delta {delta})')
            elif left[field] != right[field]:
                raise ValueError(f'checkpoint {index} {field}: {left[field]} / {right[field]}')
    if scenario == 'save-weapons':
        validate_save_weapons(native, tolerance)
        return len(native)
    if scenario == 'explosive-weapons':
        validate_explosive_weapons(native)
        return len(native)
    if scenario == 'melee-hit':
        expected = ('chainsaw_selected', 'target_spawned', 'chainsaw_first_hit',
                    'chainsaw_followup', 'chainsaw_kill', 'chainsaw_recovery')
        if tuple(row.get('phase') for row in native) != expected:
            raise ValueError('melee-hit scenario is incomplete or out of order')
        if any(row.get('weapon') != 'weapon_chainsaw' or row['health'] <= 0 for row in native):
            raise ValueError('melee-hit: wrong weapon or player died')
        if not native[-1]['ready']:
            raise ValueError('melee-hit: weapon did not recover')
        return len(native)
    if scenario == 'bfg-damage':
        expected = ('bfg_selected', 'bfg_targets', 'bfg_charge', 'bfg_release',
                    'bfg_earlyimpact', 'bfg_impact', 'bfg_settled')
        if tuple(row.get('phase') for row in native) != expected:
            raise ValueError('BFG damage scenario is incomplete or out of order')
        if any(row.get('weapon') != 'weapon_bfg' or row['health'] <= 0 for row in native):
            raise ValueError('BFG damage: wrong weapon or player died')
        if native[3]['ammo'] >= native[2]['ammo'] or native[4]['health'] >= native[3]['health']:
            raise ValueError('BFG did not consume ammo and exercise player splash damage')
        if not native[-1]['ready']:
            raise ValueError('BFG did not recover')
        return len(native)
    if scenario == 'bfg-beam':
        expected = ('beam_selected', 'beam_settle', 'beam_target', 'beam_charge', 'beam_release',
                    'beam_before_damage', 'beam_damage1', 'beam_damage2', 'beam_impact', 'beam_ragdoll', 'beam_recovery', 'beam_removed')
        if tuple(row.get('phase') for row in native) != expected:
            raise ValueError('periodic beam scenario is incomplete or out of order')
        if any(row.get('weapon') != 'weapon_bfg' or row['health'] <= 0 for row in native):
            raise ValueError('periodic beam: wrong weapon or player died')
        if native[4]['ammo'] >= native[3]['ammo'] or not native[-1]['ready']:
            raise ValueError('periodic beam: ammunition/recovery was not exercised')
        return len(native)
    if len({row['origin'] for row in native}) < 4:
        raise ValueError('sequence did not exercise enough distinct physical positions')
    if not any(row['ground'] == 0 for row in native) or not any(row['crouch'] for row in native):
        raise ValueError('sequence did not exercise jump and crouch')
    clips = [row['clip'] for row in native if row['clip'] >= 0]
    if not clips or len(set(clips)) < 2 or clips[-1] <= min(clips):
        raise ValueError('sequence did not exercise ammunition consumption and reload')
    return len(native)


def validate_explosive_weapons(rows):
    groups = {
        'grenade': ('weapon_handgrenade', ('selected', 'hold', 'release', 'flight', 'flight2', 'end', 'removed')),
        'rocket': ('weapon_rocketlauncher', ('selected', 'fire', 'flight', 'recovery', 'reload')),
        'bfg': ('weapon_bfg', ('selected', 'charge', 'release', 'flight', 'recovery', 'reload', 'removed')),
        'chainsaw': ('weapon_chainsaw', ('selected', 'attack', 'recovery')),
    }
    expected = [f'{name}_{phase}' for name, (_, phases) in groups.items() for phase in phases]
    if [row.get('phase') for row in rows] != expected:
        raise ValueError('explosive/melee scenario is incomplete or out of order')
    for name, (weapon, phases) in groups.items():
        group = [row for row in rows if row['phase'].startswith(name + '_')]
        if any(row.get('weapon') != weapon or row['health'] <= 0 for row in group):
            raise ValueError(f'{name}: wrong weapon or player died before coverage completed')
        if name == 'chainsaw':
            if not group[-1]['ready']:
                raise ValueError('chainsaw: attack did not recover')
            continue
        if min(row['ammo'] for row in group[1:]) >= group[0]['ammo']:
            raise ValueError(f'{name}: firing did not consume ammunition')
        if name in ('rocket', 'bfg'):
            reloaded = next(row for row in group if row['phase'] == name + '_reload')
            if reloaded['clip'] <= min(row['clip'] for row in group[1:]) or not reloaded['ready']:
                raise ValueError(f'{name}: reload did not complete')


def validate_save_weapons(rows, tolerance):
    phases = {name: [row for row in rows if row.get('phase') == name]
              for name in ('save_before', 'changed', 'save_after', 'shotgun',
                           'machinegun', 'chaingun', 'plasmagun')}
    if [len(group) for group in phases.values()] != [1, 3, 2, 4, 4, 4, 4]:
        raise ValueError('save/weapon scenario is incomplete')
    saved, loaded = phases['save_before'][0], phases['save_after'][0]
    for field in ('origin', 'velocity', 'view', 'ground', 'crouch', 'health', 'weapon', 'clip', 'ammo', 'ready'):
        if field not in saved or field not in loaded:
            raise ValueError(f'missing save evidence: {field}')
        if field in ('origin', 'velocity', 'view'):
            if max(abs(a-b) for a, b in zip(saved[field], loaded[field])) > tolerance:
                raise ValueError(f'save/load did not restore {field}')
        elif saved[field] != loaded[field]:
            raise ValueError(f'save/load did not restore {field}')
    if abs(saved['view'][1]) < 1 or saved['weapon'] != 'weapon_pistol':
        raise ValueError('save did not exercise a nonzero view angle and selected pistol')
    if not saved['ground']:
        raise ValueError('save checkpoint must be settled on the floor')
    changed = phases['changed'][-1]
    if changed['origin'] == saved['origin'] or changed['clip'] >= saved['clip']:
        raise ValueError('position/ammunition were not changed before restore')
    for phase in ('shotgun', 'machinegun', 'chaingun', 'plasmagun'):
        selected, fired, recovered, reloaded = phases[phase]
        if any(row.get('weapon') != 'weapon_' + phase for row in phases[phase]):
            raise ValueError(f'{phase}: wrong weapon identity')
        if fired['clip'] >= selected['clip'] or fired['ammo'] >= selected['ammo']:
            raise ValueError(f'{phase}: firing did not consume ammunition')
        if reloaded['clip'] <= fired['clip'] or not reloaded['ready']:
            raise ValueError(f'{phase}: reload did not complete')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native_log')
    parser.add_argument('web_log')
    parser.add_argument('--scenario', choices=('movement', 'save-weapons', 'explosive-weapons', 'melee-hit', 'bfg-damage', 'bfg-beam'), default='movement')
    args = parser.parse_args()
    count = compare(checkpoints(args.native_log), checkpoints(args.web_log), scenario=args.scenario)
    print(f'PASS: {count} native/web simulation checkpoints (position/velocity tolerance 0.001 units)')
