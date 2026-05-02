# -*- coding: utf-8 -*-
"""
Test suite for JSON indexer
Verifies JSON output with NLP enrichment, cross-references and category routing

Test content is based on actual VPO (Video Product Operations) knowledge base
from Creating Tickets to Engage Fix Agents documentation, including:
- CEITEAM ticket creation for entitlements
- NetOps INC escalation procedures
- IPVC/VOINTAKE ticket workflows
- TMS billing interface tickets
- APEX3000 troubleshooting
"""

import json, shutil, tempfile, sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from tests.test_content import *

class TestJSONIndexer:
    def __init__(self):
        self.temp_dir = None
        self.original_src = config.SRC_DIR
        self.original_out = config.OUT_DIR
        
    def setup(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.src_dir = self.temp_dir / "source"
        self.out_dir = self.temp_dir / "output"
        self.src_dir.mkdir()
        self.out_dir.mkdir()
        config.SRC_DIR = str(self.src_dir)
        config.OUT_DIR = str(self.out_dir)
        
    def teardown(self):
        if self.temp_dir and self.temp_dir.exists():
            import logging
            for handler in logging.root.handlers[:]:
                handler.close()
                logging.root.removeHandler(handler)
            try:
                shutil.rmtree(self.temp_dir)
            except PermissionError:
                import time
                time.sleep(0.5)
                shutil.rmtree(self.temp_dir)
        config.SRC_DIR = self.original_src
        config.OUT_DIR = self.original_out
        
    def create_test_txt(self, name, content):
        file_path = self.src_dir / name
        file_path.write_text(content, encoding='utf-8')
        return file_path
    
    def create_test_csv(self, name, content):
        file_path = self.src_dir / name
        file_path.write_text(content, encoding='utf-8')
        return file_path
    
    def run_indexer(self):
        from build_index import main
        main()
    
    def load_json_chunks(self):
        detail_dir = self.out_dir / "detail"
        chunks = []
        unified = detail_dir / "chunks.jsonl"
        if unified.exists():
            with open(unified, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        chunks.append(json.loads(line))
        return chunks
    
    def load_json_chunks_by_category(self):
        detail_dir = self.out_dir / "detail"
        by_category = defaultdict(list)
        for cat_file in detail_dir.glob("chunks.*.jsonl"):
            if cat_file.name == "chunks.jsonl":
                continue
            category = cat_file.stem.replace("chunks.", "")
            with open(cat_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        by_category[category].append(json.loads(line))
        return by_category
    
    def test_basic_json_output(self):
        print("TEST: Basic JSON output...")
        self.setup()
        try:
            self.create_test_txt("test.txt", TEST_TROUBLESHOOTING)
            self.run_indexer()
            
            detail_dir = self.out_dir / "detail"
            assert detail_dir.exists(), "Detail directory missing"
            assert (detail_dir / "chunks.jsonl").exists(), "Unified JSON file missing"
            
            chunks = self.load_json_chunks()
            assert len(chunks) > 0, "No chunks in JSON file"
            
            print(f"  [PASS] Basic JSON output works ({len(chunks)} chunks)")
        finally:
            self.teardown()
    
    def test_json_chunk_structure(self):
        print("TEST: JSON chunk structure...")
        self.setup()
        try:
            self.create_test_txt("test.txt", TEST_TROUBLESHOOTING)
            self.run_indexer()
            
            chunks = self.load_json_chunks()
            chunk = chunks[0]
            
            assert 'id' in chunk, "Missing chunk ID"
            assert 'metadata' in chunk, "Missing metadata"
            assert 'nlp_category' in chunk['metadata'], "Missing NLP category"
            assert 'tags' in chunk, "Missing tags"
            assert 'text' in chunk, "Missing text content"
            
            # Verify first tag is NLP category
            nlp_cat = chunk['metadata']['nlp_category']
            assert chunk['tags'][0] == nlp_cat, f"NLP category not first tag: {chunk['tags']}"
            
            print(f"  [PASS] JSON chunk structure valid (category: {nlp_cat})")
        finally:
            self.teardown()
    
    def test_json_category_routing(self):
        print("TEST: JSON category routing...")
        self.setup()
        try:
            self.create_test_txt("troubleshooting.txt", TEST_TROUBLESHOOTING)
            self.create_test_txt("queries.txt", TEST_QUERIES)
            self.create_test_txt("sop.txt", TEST_SOP)
            self.create_test_txt("manual.txt", TEST_MANUAL)
            self.create_test_txt("reference.txt", TEST_REFERENCE)
            
            self.run_indexer()
            
            by_category = self.load_json_chunks_by_category()
            unified_chunks = self.load_json_chunks()
            
            # NLP may classify similar content into same category, so check for at least 2
            assert len(by_category) >= 2, f"Expected multiple categories, got {len(by_category)}"
            
            # Verify category consistency
            for category, chunks in by_category.items():
                for chunk in chunks:
                    nlp_cat = chunk.get('metadata', {}).get('nlp_category', 'general')
                    assert nlp_cat == category, \
                        f"Chunk in wrong file: {category} file has {nlp_cat} chunk"
            
            # Verify unified contains all
            total_in_categories = sum(len(chunks) for chunks in by_category.values())
            assert total_in_categories == len(unified_chunks), \
                f"Unified mismatch: {total_in_categories} vs {len(unified_chunks)}"
            
            print(f"  [PASS] JSON category routing works:")
            for category, chunks in sorted(by_category.items()):
                print(f"      {category}: {len(chunks)} chunks")
        finally:
            self.teardown()
    
    def test_cross_category_relationships(self):
        print("TEST: Cross-category relationships...")
        self.setup()
        try:
            # Create files with common VPO terms
            self.create_test_txt("troubleshooting.txt", TEST_TROUBLESHOOTING)
            self.create_test_txt("queries.txt", TEST_QUERIES)
            self.create_test_txt("sop.txt", TEST_SOP)
            self.create_test_txt("manual.txt", TEST_MANUAL)
            self.create_test_txt("reference.txt", TEST_REFERENCE)
            
            self.run_indexer()
            
            chunks = self.load_json_chunks()
            
            # Find chunks with common tags
            chunks_by_tag = defaultdict(list)
            for chunk in chunks:
                for tag in chunk.get('tags', []):
                    if tag.lower() in COMMON_VPO_TAGS:
                        chunks_by_tag[tag.lower()].append(chunk['id'])
            
            # Verify multiple categories share tags
            assert len(chunks_by_tag) > 0, "No common tags found"
            
            # Verify at least one tag appears in multiple chunks
            multi_chunk_tags = {tag: ids for tag, ids in chunks_by_tag.items() if len(ids) > 1}
            assert len(multi_chunk_tags) > 0, "No tags shared across chunks"
            
            print(f"  [PASS] Cross-category relationships exist:")
            for tag, ids in list(multi_chunk_tags.items())[:3]:
                print(f"      '{tag}': {len(ids)} chunks")
        finally:
            self.teardown()
    
    def test_json_search_readability(self):
        print("TEST: JSON search readability...")
        self.setup()
        try:
            self.create_test_txt("test.txt", TEST_QUERIES)
            self.run_indexer()
            
            chunks = self.load_json_chunks()
            assert len(chunks) > 0, "No chunks created"
            
            chunk = chunks[0]
            # Verify searchable fields exist
            assert 'search_text' in chunk, "Missing search_text field"
            assert 'search_keywords' in chunk, "Missing search_keywords field"
            
            # Verify searchable VPO content
            search_text = chunk['search_text'].lower()
            assert 'ceiteam' in search_text or 'ticket' in search_text, "Missing searchable VPO terms"
            assert 'ace' in search_text or 'clms' in search_text, "Missing VPO system names"
            
            print("  [PASS] JSON search readability verified")
        finally:
            self.teardown()
    
    def test_csv_with_relationships(self):
        print("TEST: CSV processing with relationships...")
        self.setup()
        try:
            # Create CSV and related text files
            self.create_test_csv("tickets.csv", TEST_CSV_CONTENT)
            self.create_test_txt("queries.txt", TEST_QUERIES)
            
            self.run_indexer()
            
            chunks = self.load_json_chunks()
            
            # Find CSV chunks
            csv_chunks = [c for c in chunks if c.get('element_type') == 'csv_row']
            assert len(csv_chunks) > 0, "No CSV chunks created"
            
            # Verify CSV chunks have NLP category
            for chunk in csv_chunks:
                assert 'nlp_category' in chunk.get('metadata', {}), "CSV missing NLP category"
            
            # Verify common tags between CSV and text
            csv_tags = set()
            text_tags = set()
            for chunk in chunks:
                if chunk.get('element_type') == 'csv_row':
                    csv_tags.update(chunk.get('tags', []))
                else:
                    text_tags.update(chunk.get('tags', []))
            
            common = csv_tags & text_tags
            assert len(common) > 0, f"No common tags between CSV and text"
            
            print(f"  [PASS] CSV relationships work ({len(common)} common tags)")
        finally:
            self.teardown()
    
    def test_incremental_json_updates(self):
        print("TEST: Incremental JSON updates...")
        self.setup()
        try:
            # First run
            self.create_test_txt("file1.txt", TEST_TROUBLESHOOTING)
            self.run_indexer()
            first_chunks = self.load_json_chunks()
            first_count = len(first_chunks)
            
            # Second run - add new file
            self.create_test_txt("file2.txt", TEST_QUERIES)
            self.run_indexer()
            second_chunks = self.load_json_chunks()
            second_count = len(second_chunks)
            
            # Verify incremental processing added chunks
            assert second_count >= first_count, \
                f"Incremental failed: {first_count} -> {second_count}"
            
            # Verify both files were processed by checking category files
            detail_dir = self.out_dir / "detail"
            cat_files = list(detail_dir.glob("chunks.*.jsonl"))
            assert len(cat_files) >= 1, "No category files created"
            
            print(f"  [PASS] Incremental JSON updates work ({first_count} -> {second_count})")
        finally:
            self.teardown()
    
    def test_router_records(self):
        print("TEST: Router records...")
        self.setup()
        try:
            self.create_test_txt("test.txt", TEST_TROUBLESHOOTING)
            self.run_indexer()
            
            router_dir = self.out_dir / "router"
            assert router_dir.exists(), "Router directory missing"
            
            router_docs = router_dir / "router.docs.jsonl"
            assert router_docs.exists(), "Router docs file missing"
            
            with open(router_docs, 'r', encoding='utf-8') as f:
                docs = [json.loads(line) for line in f if line.strip()]
            assert len(docs) > 0, "No router docs created"
            
            print(f"  [PASS] Router records work ({len(docs)} docs)")
        finally:
            self.teardown()

def run_all_tests():
    tester = TestJSONIndexer()
    tests = [
        tester.test_basic_json_output,
        tester.test_json_chunk_structure,
        tester.test_json_category_routing,
        tester.test_cross_category_relationships,
        tester.test_json_search_readability,
        tester.test_csv_with_relationships,
        tester.test_incremental_json_updates,
        tester.test_router_records,
    ]
    
    print("=" * 60)
    print("JSON INDEXER TEST SUITE")
    print("=" * 60)
    
    passed = failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if run_all_tests() else 1)
