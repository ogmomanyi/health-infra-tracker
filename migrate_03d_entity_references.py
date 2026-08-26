#!/usr/bin/env python3
"""Migrate organisation references into the canonical 03D namespace."""
import hashlib
import sqlite3
from organisation_resolution.normalizer import normalize_name

DB = "data/iati_intelligence.db"
LEGACY_ENTITIES = "organisation_entities_intelligence_legacy"
AUDIT_TABLE = "organisation_relationship_migration_audit"

def table_exists(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None

def columns(conn, table):
    return {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}

def build_canonical_map(conn):
    ids = {r[0] for r in conn.execute("SELECT entity_id FROM organisation_entities")}
    parents = {child: parent for parent, child in conn.execute("SELECT parent_entity_id, child_entity_id FROM organisation_relationships WHERE relationship_type='DUPLICATE_OF'")}
    def root(eid):
        if eid not in ids: return None
        seen=set(); cur=eid
        while cur in parents:
            if cur in seen: raise RuntimeError(f"Cycle detected in DUPLICATE_OF relationships at {cur}")
            seen.add(cur); cur=parents[cur]
            if cur not in ids: return None
        return cur
    return {eid: root(eid) for eid in ids}

def build_legacy_map(conn, canonical_map):
    if not table_exists(conn, LEGACY_ENTITIES): return {}, {}
    by_name={}
    for eid,name,status in conn.execute("SELECT entity_id, canonical_name, entity_status FROM organisation_entities"):
        if status not in (None,'ACTIVE'): continue
        key=normalize_name(name); root=canonical_map.get(eid)
        if key and root: by_name.setdefault(key,set()).add(root)
    mapping={}; unresolved={}
    for legacy_id,name in conn.execute(f"SELECT organisation_entity_id, canonical_name FROM {LEGACY_ENTITIES}"):
        # Only ORG-* IDs are semantically legacy. Current org_* IDs must be
        # resolved directly through the canonical map, not by historical name.
        if not str(legacy_id).startswith('ORG-'): continue
        candidates=by_name.get(normalize_name(name),set())
        if len(candidates)==1: mapping[legacy_id]=next(iter(candidates))
        else: unresolved[legacy_id]=sorted(candidates)
    return mapping, unresolved

def resolve(eid, mapping, canonical_map):
    mapped=mapping.get(eid,eid)
    return canonical_map.get(mapped,mapped)

def migrate_column(conn, table, column, mapping, canonical_map):
    if not table_exists(conn,table) or column not in columns(conn,table): return 0
    changed=0
    for rowid,old in conn.execute(f'SELECT rowid,"{column}" FROM "{table}" WHERE "{column}" IS NOT NULL').fetchall():
        new=resolve(old,mapping,canonical_map)
        if new and new!=old:
            conn.execute(f'UPDATE "{table}" SET "{column}"=? WHERE rowid=?',(new,rowid)); changed+=1
    return changed

def ensure_audit(conn):
    conn.execute(f'''CREATE TABLE IF NOT EXISTS {AUDIT_TABLE} (
        audit_id INTEGER PRIMARY KEY AUTOINCREMENT, relationship_id TEXT NOT NULL,
        parent_entity_id TEXT NOT NULL, child_entity_id TEXT NOT NULL,
        relationship_type TEXT NOT NULL, source_system TEXT, confidence_score REAL,
        created_at TIMESTAMP, mapped_parent_entity_id TEXT, mapped_child_entity_id TEXT,
        action TEXT NOT NULL, reason TEXT, audited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

def rel_id(original,parent,child,typ,source,confidence):
    payload='|'.join(map(str,(original,parent,child,typ,source,confidence)))
    return 'rel-03d-'+hashlib.sha256(payload.encode()).hexdigest()[:24]

def audit(conn,row,mapped_parent,mapped_child,action,reason):
    conn.execute(f'''INSERT INTO {AUDIT_TABLE}
        (relationship_id,parent_entity_id,child_entity_id,relationship_type,source_system,
         confidence_score,created_at,mapped_parent_entity_id,mapped_child_entity_id,action,reason)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)''',(*row[:7],mapped_parent,mapped_child,action,reason))

def rebuild_relationships(conn,mapping,canonical_map):
    if not table_exists(conn,'organisation_relationships'): return {'migrated':0,'duplicates':0,'archived':0}
    ensure_audit(conn)
    rows=conn.execute('''SELECT relationship_id,parent_entity_id,child_entity_id,relationship_type,
        source_system,confidence_score,created_at FROM organisation_relationships''').fetchall()
    if table_exists(conn,'organisation_relationships_legacy'):
        rows += conn.execute('''SELECT relationship_id,parent_entity_id,child_entity_id,relationship_type,
            source_system,confidence_score,created_at FROM organisation_relationships_legacy''').fetchall()
    conn.execute('DROP TABLE IF EXISTS organisation_relationships_03d_backup')
    conn.execute('ALTER TABLE organisation_relationships RENAME TO organisation_relationships_03d_backup')
    conn.execute('''CREATE TABLE organisation_relationships (
        relationship_id TEXT PRIMARY KEY,parent_entity_id TEXT NOT NULL,child_entity_id TEXT NOT NULL,
        relationship_type TEXT NOT NULL,source_system TEXT NOT NULL DEFAULT 'IATI',confidence_score REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(parent_entity_id) REFERENCES organisation_entities(entity_id),
        FOREIGN KEY(child_entity_id) REFERENCES organisation_entities(entity_id))''')
    seen=set(); used=set(); stats={'migrated':0,'duplicates':0,'archived':0}
    for row in rows:
        rid,parent,child,typ,source,confidence,created=row
        mp=resolve(parent,mapping,canonical_map); mc=resolve(child,mapping,canonical_map)
        pexists=conn.execute('SELECT 1 FROM organisation_entities WHERE entity_id=?',(mp,)).fetchone()
        cexists=conn.execute('SELECT 1 FROM organisation_entities WHERE entity_id=?',(mc,)).fetchone()
        if not pexists or not cexists:
            stats['archived']+=1
            audit(conn,row,mp,mc,'ARCHIVED_LEGACY','orphaned historical relationship has no current canonical endpoint; preserved in audit')
            continue
        if mp==mc and typ=='DUPLICATE_OF':
            stats['duplicates']+=1; audit(conn,row,mp,mc,'DUPLICATE','relationship collapses to one canonical entity'); continue
        key=(mp,mc,typ,source,confidence)
        if key in seen:
            stats['duplicates']+=1; audit(conn,row,mp,mc,'DUPLICATE','duplicate logical relationship'); continue
        seen.add(key); new=rid
        if new in used: new=rel_id(rid,mp,mc,typ,source,confidence)
        used.add(new)
        conn.execute('''INSERT INTO organisation_relationships
            (relationship_id,parent_entity_id,child_entity_id,relationship_type,source_system,confidence_score,created_at)
            VALUES (?,?,?,?,?,?,?)''',(new,mp,mc,typ,source,confidence,created))
        stats['migrated']+=1; audit(conn,row,mp,mc,'MIGRATED','relationship rewritten into canonical namespace')
    return stats

def validate_no_legacy(conn):
    refs={'organisation_relationships':['parent_entity_id','child_entity_id'],'organisation_group_members':['entity_id'],
          'organisation_resolution_log':['entity_id'],'organisation_manual_overrides':['entity_id'],
          'opportunity_organisation_resolution':['entity_id']}
    failures={}
    for table,cols in refs.items():
        if not table_exists(conn,table): continue
        for col in cols:
            if col in columns(conn,table):
                n=conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE "{col}" LIKE \'ORG-%\'').fetchone()[0]
                if n: failures[f'{table}.{col}']=n
    if failures: raise RuntimeError(f'Legacy ORG-* references remain: {failures}')

def main():
    conn=sqlite3.connect(DB)
    try:
        conn.execute('PRAGMA foreign_keys=OFF'); conn.execute('BEGIN')
        cmap=build_canonical_map(conn); mapping,unresolved=build_legacy_map(conn,cmap)
        if unresolved: raise RuntimeError('Unresolved legacy ORG-* entity mappings; refusing to guess: '+repr(unresolved))
        print(f'Legacy entity mappings available: {len(mapping)}')
        changed={}
        for table in ('organisation_intelligence','target_accounts','recommended_actions','programme_intelligence','donor_intelligence','equipment_entities','opportunity_organisation_resolution','organisation_resolution_log','organisation_manual_overrides'):
            changed[table]=migrate_column(conn,table,'organisation_entity_id',mapping,cmap)
            changed[table+'.entity_id']=migrate_column(conn,table,'entity_id',mapping,cmap)
        changed['organisation_group_members']=migrate_column(conn,'organisation_group_members','entity_id',mapping,cmap)
        changed['organisation_relationships']=rebuild_relationships(conn,mapping,cmap)
        validate_no_legacy(conn); conn.commit()
        for k,v in changed.items(): print(f'{k}: {v}')
        print('03D entity-reference migration PASSED')
    except Exception:
        conn.rollback(); raise
    finally: conn.close()
if __name__=='__main__': main()
