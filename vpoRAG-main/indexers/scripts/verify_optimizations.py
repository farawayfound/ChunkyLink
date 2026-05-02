# -*- coding: utf-8 -*-
"""
Verification script for vpoRAG optimizations
Checks tag quality, deduplication, and cross-reference functionality
"""

import json, sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

def verify_tag_normalization(chunks_file):
    """Check for tag quality issues"""
    print("\n=== Tag Normalization Check ===")
    issues = []
    
    with open(chunks_file, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if not line.strip():
                continue
            chunk = json.loads(line)
            tags = chunk.get("tags", [])
            
            for tag in tags:
                # Check for newlines
                if '\n' in tag or '\r' in tag:
                    issues.append(f"Line {i}: Tag contains newline: '{tag}'")
                # Check for excessive length
                if len(tag) > 50:
                    issues.append(f"Line {i}: Tag too long ({len(tag)} chars): '{tag[:50]}...'")
                # Check for multiple hyphens
                if '--' in tag:
                    issues.append(f"Line {i}: Tag has multiple hyphens: '{tag}'")
    
    if issues:
        print(f"❌ Found {len(issues)} tag issues:")
        for issue in issues[:10]:
            print(f"  {issue}")
        if len(issues) > 10:
            print(f"  ... and {len(issues) - 10} more")
    else:
        print("✅ All tags properly normalized")
    
    return len(issues) == 0

def verify_deduplication(chunks_file):
    """Check for duplicate chunks"""
    print("\n=== Deduplication Check ===")
    
    text_hashes = {}
    duplicates = []
    
    with open(chunks_file, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if not line.strip():
                continue
            chunk = json.loads(line)
            text = chunk.get("text_raw", chunk.get("text", ""))
            
            # Simple hash
            text_hash = hash(text[:500])
            
            if text_hash in text_hashes:
                duplicates.append((i, text_hashes[text_hash], text[:100]))
            else:
                text_hashes[text_hash] = i
    
    if duplicates:
        print(f"❌ Found {len(duplicates)} potential duplicates:")
        for i, orig, text in duplicates[:5]:
            print(f"  Line {i} duplicates line {orig}: '{text}...'")
        if len(duplicates) > 5:
            print(f"  ... and {len(duplicates) - 5} more")
    else:
        print("✅ No duplicate chunks found")
    
    return len(duplicates) == 0

def verify_cross_references(chunks_file):
    """Check cross-reference quality"""
    print("\n=== Cross-Reference Check ===")
    
    total_chunks = 0
    chunks_with_refs = 0
    total_refs = 0
    chunks_with_keywords = 0
    chunks_with_clusters = 0
    
    with open(chunks_file, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            chunk = json.loads(line)
            total_chunks += 1
            
            related = chunk.get("related_chunks", [])
            if related:
                chunks_with_refs += 1
                total_refs += len(related)
            
            if chunk.get("search_keywords"):
                chunks_with_keywords += 1
            
            if chunk.get("topic_cluster_id"):
                chunks_with_clusters += 1
    
    if total_chunks == 0:
        print("❌ No chunks found")
        return False
    
    avg_refs = total_refs / total_chunks
    ref_coverage = (chunks_with_refs / total_chunks) * 100
    keyword_coverage = (chunks_with_keywords / total_chunks) * 100
    cluster_coverage = (chunks_with_clusters / total_chunks) * 100
    
    print(f"Total chunks: {total_chunks}")
    print(f"Chunks with related_chunks: {chunks_with_refs} ({ref_coverage:.1f}%)")
    print(f"Average related chunks: {avg_refs:.2f}")
    print(f"Chunks with search_keywords: {chunks_with_keywords} ({keyword_coverage:.1f}%)")
    print(f"Chunks with topic_cluster_id: {chunks_with_clusters} ({cluster_coverage:.1f}%)")
    
    if keyword_coverage > 80 and cluster_coverage > 80:
        print("✅ Cross-references properly built")
        return True
    else:
        print("⚠️  Cross-references may be incomplete (run build_cross_references.py)")
        return False

def verify_metadata_reduction(chunks_file):
    """Check metadata size reduction"""
    print("\n=== Metadata Reduction Check ===")
    
    old_fields = ["chapter_title", "breadcrumb", "hierarchy_level", "section_title", "section_id", "bbox"]
    chunks_with_old_fields = 0
    total_chunks = 0
    
    with open(chunks_file, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            chunk = json.loads(line)
            total_chunks += 1
            
            metadata = chunk.get("metadata", {})
            if any(field in metadata for field in old_fields):
                chunks_with_old_fields += 1
    
    if chunks_with_old_fields > 0:
        print(f"⚠️  {chunks_with_old_fields}/{total_chunks} chunks have old metadata fields")
        print("   (Rebuild index to apply metadata reduction)")
    else:
        print("✅ Metadata properly reduced")
    
    return chunks_with_old_fields == 0

def main():
    out_dir = Path(config.OUT_DIR)
    chunks_file = out_dir / "detail" / "chunks.jsonl"
    
    if not chunks_file.exists():
        print(f"❌ Chunks file not found: {chunks_file}")
        print("   Run build_index_with_cross_refs.py first")
        return
    
    print(f"Verifying optimizations in: {chunks_file}")
    
    results = {
        "tag_normalization": verify_tag_normalization(chunks_file),
        "deduplication": verify_deduplication(chunks_file),
        "cross_references": verify_cross_references(chunks_file),
        "metadata_reduction": verify_metadata_reduction(chunks_file)
    }
    
    print("\n=== Summary ===")
    passed = sum(results.values())
    total = len(results)
    
    for check, result in results.items():
        status = "✅" if result else "❌"
        print(f"{status} {check.replace('_', ' ').title()}")
    
    print(f"\nPassed: {passed}/{total} checks")
    
    if passed == total:
        print("\n🎉 All optimizations verified successfully!")
    else:
        print("\n⚠️  Some optimizations need attention (see details above)")

if __name__ == "__main__":
    main()
