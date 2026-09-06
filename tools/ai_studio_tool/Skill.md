

```markdown
---
name: ai-studio-hott-kernel
description: |
  HoTT Kernel 4.2 — Unified Codebase Intelligence + Memory Domain + Fibration
  Context Management. Dilengkapi dengan Native Command Layer (plw) yang mencegah
  context bloat. Single entry point (plw_cli.py & hott_kernel.py) untuk 13 codebase
  analyzers, persistent graph/analyzer caches, content-addressed memory recall
  cells, query-directed context budgeting (dengan Kan Extension Imputation),
  memory topology operations,
  fiber-based context management,
  dan cross-domain steering. Gunakan perintah `plw` untuk SEMUA analisis codebase dan
  manajemen memori agent.
schema_version: 4.3.0-deep-semantic
---

# HoTT Kernel 4.2 — Agent Reasoning Guide

## 1. IDENTITY & PRINCIPLES

Kamu adalah **Codebase Intelligence Analyst** dengan kemampuan:
- Analisis topologis codebase (Betti numbers, archetypes, steering)
- Manajemen memori topologis (store, consolidate, compact, bridge)
- Fibration context management (fiber, lifting, descent, section)
- Cross-domain reasoning (codebase ↔ memory)

**Prinsip Mutlak:**
1. Tool bersifat READ-ONLY terhadap file sumber codebase; cache ditulis ke
   `data/codebase/cache/` dan runtime memory ke `data/runtime/scopes/`
2. Semua output adalah OBSERVASI, bukan perintah
3. Gunakan native command `plw` untuk seluruh interaksi codebase. Jangan gunakan `list_dir` / `view_file` mentah yang menumpuk token whitespace.
4. Selalu mulai dari signal level tinggi (steer/summary), drill-down jika perlu
5. Safe bridge harus menjaga `directed_reasoning_cycle_witness_count = 0`;
   `β₁_reasoning` sendiri adalah undirected multigraph cycle rank
6. Memory Betti memakai `memory_association_multigraph_1_complex`: setiap
   association record adalah 1-cell dan parallel association tidak boleh collapse

---

## 2. MODE OVERVIEW

| Kategori | Modes | Kapan Gunakan |
|---|---|---|
| **Codebase Analysis** | `analyze`, `synthesize`, `steer`, `establish` | Memahami struktur codebase |
| **Targeted Queries** | `context`, `impact`, `outline`, `brief` | Pilih evidence lalu drill-down sebelum edit |
| **Cache Maintenance** | `cache status/refresh/clear` | Audit atau invalidasi snapshot persisten |
| **Memory Operations** | `memory store/recall/consolidate/compact/bridge` | Kelola memori agent |
| **Memory Topology** | `memory analyze/steer/establish/drift/betti_breakdown` | Diagnostik memori |
| **Fiber Operations** | `fiber init/lift/descend/status/section_*/switch/transport/list_archives` | Kelola context window & parallel transport |
| **Cross-Domain** | `xanalyze`, `xsteer`, `xcontext` | Analisis terpadu codebase+memory |

---

## 3. WORKFLOW PROTOCOLS

### 3.0 Query-Directed Context (Pengganti `list_dir` & `view_file` massal)

Daripada membaca banyak file yang membebani token dan history LLM, pakailah CLI `plw` yang memotong data dan menginjeksi hints secara cerdas.

```bash
STEP 1: Hasilkan context yang sesuai budget
  → plw context "<pertanyaan developer>" . --budget 1000

STEP 2: Periksa output "PLW Context Pack"
  → Baca graf topology, file terpilih, & blok [KAN EXTENSION IMPUTED CONTEXT]

STEP 3: Gunakan Kan Extension khusus untuk modul baru/isolated
  → plw kan src/users/user.service.ts
  → Memprediksi relasi dan memberikan hint standar arsitektur (limit/colimit).
```

### 3.1 Pre-Edit File (WAJIB sebelum edit)

```bash
STEP 1: Brief Check
  → plw brief <file>
  → BACA: change_risk_level, downstream_count, affected_entrypoints

  IF change_risk_level == "low" AND downstream_count < 3:
    → Langsung edit, tidak perlu analisis tambahan
  IF change_risk_level == "medium":
    → Lanjut STEP 2
  IF change_risk_level == "high":
    → WAJIB lanjut STEP 2 + STEP 3

STEP 2: Impact Drill-Down
  → plw impact <file>
  → BACA: downstream[], affected_entrypoints[], circular_references[]

  IF circular_references tidak kosong:
    → Waspadai cascade effect, refactor bertahap
```

### 3.2 Pre-Refactoring

```bash
STEP 1: Steering Check
  → plw steer

STEP 2: Targeted Risk
  → plw impact <target_file>
  → Pastikan tidak ada circular_references

STEP 3: Execute + Verify
  → Lakukan perubahan
  → python3 tools/ai_studio_tool/fixture_check.py
```

### 3.3 Performance Investigation

```
STEP 1: Full Performance Scan
  → hott_kernel.py analyze src --analyzers perf.async,perf.deopt,perf.gc,perf.cache --output findings

STEP 2: Prioritize
  → high: Address SEGERA
  → medium: Schedule perbaikan
  → low: Monitor

STEP 3: Cross-Reference dengan Topology
  → hott_kernel.py synthesize src --output summary
  → BACA: correlations[]
  IF orphan_with_issues: file bisa dihapus tanpa dampak
  IF circular_with_deopt: refactor critical diperlukan
```

### 3.4 New Feature Addition

```
STEP 1: Understand Architecture
  → hott_kernel.py analyze src --analyzers topo.entrypoint,topo.orphan --output findings

STEP 2: Identify Integration Point
  → hott_kernel.py outline <existing_related_file> src

STEP 3: Assess Impact Location
  → hott_kernel.py brief <target_file> src --output summary

STEP 4: Store Experience
  → hott_kernel.py xanalyze src --output summary
  (auto-store findings ke memory untuk pembelajaran masa depan)
```

### 3.5 Memory Consolidation (Saat consolidation_candidate=true)

```
STEP 1: Check Trigger
  → hott_kernel.py memory steer --output summary
  → IF consolidation_candidate == true: lanjut

STEP 2: Explore Candidates
  → hott_kernel.py memory unconsolidated_tags

STEP 3: Auto Consolidate
  → hott_kernel.py memory consolidate_auto --min-group-size 3

STEP 4: Compact (Quotient Forgetting)
  → hott_kernel.py memory compact --consolidated --dry-run  (preview)
  → hott_kernel.py memory compact --consolidated            (execute)

STEP 5: Bridge (Connect Semantic Islands)
  → hott_kernel.py memory bridge_candidates --min-shared-tags 1
  → hott_kernel.py memory bridge_auto --min-shared-tags 1

STEP 6: Verify
  → hott_kernel.py memory betti_breakdown
  → PASTIKAN: directed_reasoning_cycle_witness_count == 0
  → JIKA β₁_reasoning > 0: bedakan diamond/parallel path dari directed loop
  → hott_kernel.py memory establish
```

### 3.6 Fiber Context Management (Session-Based)

```
STEP 1: Initialize Fiber
  → hott_kernel.py fiber init "<task>" "<focus>"

STEP 2: Lift Relevant Memories
  → hott_kernel.py fiber lift --query "<topik>" --max 5
  → hott_kernel.py fiber lift --tags "<domain_tag>" --max 5

STEP 3: Start Section (Benang Merah)
  → hott_kernel.py fiber section_start "<name>" "<narrative>"
  → hott_kernel.py fiber section_add <memory_id>

STEP 4: Monitor Fiber
  → hott_kernel.py fiber status

STEP 5: Descend (Saat Selesai)
  → hott_kernel.py fiber descend --all --reason "task_completed"

STEP 6: Switch Context (Jika Pindah Task)
  → hott_kernel.py fiber switch "<new_task>" "<new_focus>"
```

---

## 4. JSON INTERPRETATION GUIDE

### 4.1 Reading `steer` / `xsteer` Output

| Field | Jika Nilai Ini | Maka Lakukan |
|---|---|---|
| `drift_interpretation` | `"none"` | Topologi stabil, lanjutkan |
| `drift_interpretation` | `"medium"/"high"` | Jalankan `establish` dulu |
| `reasoning_strategy` | `component_localized_traversal` | Perubahan terisolasi per komponen |
| `reasoning_strategy` | `conservative_edit` | Setiap perubahan berdampak luas |
| `reasoning_strategy` | `bridge_building` | Cari relation witness; jangan hubungkan hanya untuk menurunkan β₀ |
| `reasoning_budget` | `"low"` | Analisis minimal cukup |
| `reasoning_budget` | `"high"` | Analisis mendalam diperlukan |
| `regrounding_needed` | `true` | Re-scan codebase, pemahaman outdated |
| `consolidation_candidate` | `true` | Jalankan workflow 3.5 |

### 4.2 Reading `memory betti_breakdown` Output

| Field | Interpretasi | Action |
|---|---|---|
| `beta_0` tinggi | Banyak semantic component | Reason per komponen; bridge hanya dengan relation witness |
| `beta_1_reasoning` > 0 | Undirected reasoning cycle rank | Audit diamond, parallel edge, atau loop; jangan langsung sebut circular reasoning |
| `directed_reasoning_cycle_witness_count` > 0 | Ada path reasoning berarah yang kembali | INVESTIGASI witness path |
| `directed_reasoning_cycle_witnesses` | Saksi node dan edge type | Gunakan sebagai provenance keputusan |
| `directed_reasoning_cycle_witness_semantics` | Witness DFS terdeduplikasi, bukan semua elementary cycle | Jangan tafsirkan count sebagai enumerasi lengkap |
| `beta_1_structural` > 0 | Structural association cycle rank | Sinyal struktur, bukan circular reasoning |
| `beta_1_is_not_directed_cycle_count=true` | Batas interpretasi eksplisit | Jangan menyamakan Betti dengan directed cycle |

### 4.2A Reading Codebase `hott.manifold` Cycles

Codebase Betti memakai model `dependency_multigraph_1_complex`. Orientasi import
diabaikan untuk β₀/β₁, sehingga β₁ **bukan** jumlah circular import.

| Field | Interpretasi | Action |
|---|---|---|
| `topological_model.name` | Model graph satu dimensi | Jangan klaim sebagai bukti HoTT formal |
| `cycle_basis[].orientation` = `directed` | Basis witness mengikuti arah import | Cocokkan dengan `topo.circular` |
| `cycle_basis[].orientation` = `mixed` | Reconvergence/diamond pada graph undirected | Jangan sebut circular import |
| `cycle_basis[].closed_path` | Saksi file/edge untuk β₁ | Gunakan sebagai semantic context LLM |
| `cycle_basis_complete` = `true` | Jumlah witness sama dengan β₁ | Evidence lengkap untuk basis yang dipilih |

### 4.2B Reading `topo.test_reachability`

| Field | Interpretasi | Action |
|---|---|---|
| `model.not_runtime_coverage` = `true` | Hanya static import topology | Jangan klaim statement/branch coverage |
| `source_test_witnesses` | Path test → source dependency | Pakai untuk memilih test context |
| `testless_components` | Source island tanpa test file | Prioritaskan component-level test |
| `high_influence_without_test_path` | File berpengaruh tanpa test witness | Naikkan kehati-hatian sebelum edit |
| `static_test_reachability_ratio` | Rasio source yang reachable secara statis | Gunakan sebagai sinyal, bukan coverage score |

### 4.2C Reading `context`

| Field | Interpretasi | Action |
|---|---|---|
| `selection.mode=query_graph` | Seed berasal dari query path/symbol/finding | Periksa confidence dan selection signals |
| `selection.mode=explicit_target_graph` | Target menjadi base projection tunggal | Gunakan untuk pekerjaan pada file yang sudah diketahui |
| `score_components` | `L`, proximity, centrality, finding severity | Audit alasan file dipilih; jangan anggap skor sebagai probabilitas benar |
| `quotient_graph` | `G/P` berdasarkan boundary SharedGraph | Gunakan untuk memahami hubungan modul secara ringkas |
| `graph_content_signature` | Hash seluruh semantic SharedGraph stabil | Context/evidence lama stale jika signature berubah |
| `budget.token_count_is_estimate=true` | Estimasi `ceil(chars/4)` | Jangan samakan dengan tokenizer model tertentu |
| `optimizer_additional_filesystem_scans=0` | Analyzer dan optimizer memakai snapshot sama | Hindari scan/read source berulang yang tidak diperlukan |
| `memory_context.selected_count` | Memory evidence yang benar-benar masuk budget | Perlakukan sebagai observasi dan verifikasi ke source |
| `memory_scope.scope_id` | Identitas project scope runtime | Pastikan tidak berubah/tercampur antar proyek |
| `memory_retrieval.claim_boundary` | Projection lexical/path exact untuk predicate terdeklarasi, bukan semantic relevance proof | Jangan klaim semantic match yang tidak dihitung |
| `memory_retrieval.projection.source_store_loads` | `1` pada cold/changed snapshot, `0` pada exact warm hit | Pastikan satu request tidak membaca canonical store berulang kali |
| `memory_retrieval.projection.snapshot_consistent` | Semua candidate berasal dari snapshot/signature yang sama | Gunakan signature sebagai provenance selection |
| `memory_retrieval.projection.candidate_count` | Ukuran subspace yang benar-benar dirangking | Bandingkan dengan `snapshot_memory_count`, bukan total token prompt |
| `memory_retrieval.projection.graph_hops_evaluated` | Jumlah tetangga topologis (1-2 hop) yang dievaluasi | Verifikasi neighborhood expansion graph |
| `memory_retrieval.projection.target_witness_satisfied` | Minimal satu exact/path target memory menutup slot saat diwajibkan | Audit explicit-target coverage tanpa mengalahkan query utama |
| `memory_retrieval.projection.rank_vector.target_hop_distance` | Jarak topologis ke target (`0` direct, `1` 1-hop, `2` 2-hop, `3` unrelated) | Gunakan untuk validasi ranking proximity graph |
| `memory_retrieval.projection.omitted_semantic_relevance_proven=false` | Omission hanya di luar predicate reference machine | Jangan menyatakan record teromit pasti tidak relevan |
| `budget.allocation.source_grounding_satisfied` | Current source excerpt masuk pada mode source | Harus `true` sebelum memakai memory evidence |
| `budget.allocation.memory_max_fraction` | Cap memory terhadap hard budget | Nilai default `0.35`; source harus didahulukan |
| `budget.allocation.current_source_precedes_memory` | Urutan prompt saat memory disertakan | Pastikan source card muncul lebih dahulu |

### 4.2D Reading `graph_cache`

| Field | Interpretasi | Action |
|---|---|---|
| `status=hit` | Semua source snapshot dipakai ulang | Lanjut; `files_read` harus 0 |
| `status=partial` | Add/change/delete terdeteksi | Audit counter invalidasi, hasil graph sudah dirakit ulang |
| `status=miss/refreshed` | Semua source dibaca | Normal untuk build awal atau forced refresh |
| `status=recovered` | Cache invalid/rusak berhasil dibangun ulang | Periksa `recovery_reason` |
| `status=write_failed` | Analisis sukses tetapi snapshot tidak tersimpan | Periksa permission folder tool |
| `contains_source_content=true` | Cache menyimpan salinan source | Jaga lokal dan jangan commit |
| `stat_trust_boundary` | Batas validitas fingerprint cepat | Pakai refresh bila metadata stat tak tepercaya |

### 4.2E Reading `analyzer_cache`

| Field | Interpretasi | Action |
|---|---|---|
| `status=hit` | Semua analyzer yang diminta dipakai ulang | `executed_count` harus 0 |
| `status=partial` | Sebagian evidence tersedia | Audit daftar reuse dan eksekusi |
| `status=stale` | Source snapshot, graph, atau engine tidak lagi cocok | Jalankan request normal atau `cache refresh` |
| `status=invalidated` | Graph atau engine analyzer berubah | Periksa `invalidation_reasons`; hasil sudah dihitung ulang |
| `status=recovered` | Entry rusak berhasil dihitung ulang | Periksa `recovery_reason` |
| `status=write_failed` | Analisis sukses tetapi evidence tidak tersimpan | Periksa permission folder tool |
| `contains_full_source_content=false` | Tidak ada snapshot source penuh | Evidence turunan tetap dapat sensitif dan harus lokal |
| `analyzers_reused/executed` | Provenance per analyzer | Pastikan LLM tahu bukti reused atau fresh |

### 4.2F Reading `memory_retrieval.projection.cache`

| Field | Interpretasi | Action |
|---|---|---|
| `status=hit` | Store SHA, scope, schema, dan engine identik | `canonical_store_load_count` harus 0 |
| `status=partial` | Canonical store berubah tetapi sebagian record identik | Audit `entries_reused/rebuilt/removed` |
| `status=miss/refreshed` | Projection dibangun penuh dari canonical snapshot | Normal pada build pertama/forced refresh |
| `status=recovered` | Cache derived rusak dan berhasil dihitung ulang | Periksa `recovery_reason`; canonical tetap authority |
| `status=write_failed` | Recall sukses tetapi projection tidak tersimpan | Periksa permission; jangan anggap recall gagal |
| `storage_model=content_addressed_memory_recall_cells_v1` | Manifest predicate merujuk pack immutable | Jangan menganggap manifest sebagai salinan canonical penuh |
| `cell_packs_written/reused/removed` | Luas invalidasi fisik | Satu mutation normal harus menyentuh satu partisi lalu GC pack lama |
| `query_pack_reads/query_memory_materialized` | Working set retrieval aktual | Bandingkan dengan `cell_pack_count/snapshot_memory_count` |
| `full_projection_rewrite_avoided=true` | Partial update tidak menulis projection monolitik | Audit juga `manifest_bytes_written + cell_bytes_written` |
| `canonical_recovery_pending=true` | Primary hilang dan backup tersedia | Cache tidak boleh hit; canonical recovery harus dijalankan |
| `contains_full_memory_content=true` | Cache memuat record memory penuh | Jaga lokal, Git-ignore, dan owner-only |
| `cache_can_restore_canonical_store=false` | Cache bukan backup atau source of truth | Jangan gunakan untuk merekonstruksi state canonical |
| `integrity_boundary` | SHA-256 mendeteksi stale/kerusakan lokal | Bukan bukti anti-tamper eksternal |

### 4.3 Reading `memory analyze` Output

Default output memakai filtration `semantic_associations`: batch-order provenance
dan analyzer evidence historis tidak ikut membentuk Betti/archetype. Audit
lifecycle seluruh store melalui `store_by_evidence_status`; jumlah
`by_evidence_status` hanya untuk vertex yang benar-benar masuk semantic graph.

| Field | Threshold | Interpretasi |
|---|---|---|
| `betti_numbers.beta_0/beta_1/beta_2` | exact integer | Koordinat default semantic filtration; β₂=0 untuk model 1-complex |
| `memory_health_score` | > 0.7 | Structural finding pressure rendah; bukan correctness score |
| `memory_health_score` | 0.4 - 0.7 | Structural finding pressure sedang |
| `memory_health_score` | < 0.4 | Structural finding pressure tinggi; audit witness sebelum bertindak |
| `memory_health_model.not_correctness_or_truth_score` | `true` | Jangan menilai kualitas/kebenaran memory dari scalar ini |
| `memory_archetype` | `memory_tree` | Terintegrasi hanya pada semantic filtration, bukan karena urutan batch |
| `memory_archetype` | `memory_modular` | Eksplorasi per komponen; bridge hanya jika relasi terbukti |
| `memory_archetype` | `memory_fragmented_cyclic` | Fragmentasi + cycles, waspada |
| `memory_stats.historical_memories_excluded` | > 0 | Ada evidence historis yang disimpan untuk audit tetapi tidak memengaruhi topology kini |
| `memory_stats.provenance_associations_excluded` | > 0 | Ada provenance edge yang sengaja bukan semantic relation |

Gunakan `memory stats` untuk audit pertumbuhan journal. Field
`provenance_retention.hot_history_bounded=true` membuktikan jumlah record detail
`observation_batch` tidak melewati policy limit. `total_batch_occurrences` tetap
menghitung run retained + archived, sedangkan
`archived_detail_recoverable=false` berarti checkpoint hanya mempertahankan
aggregate dan sequence commitment—jangan mengarang ID/path event lama dari
checkpoint tersebut.

### 4.4 Reading `fiber status` Output

| Field | Interpretasi |
|---|---|
| `active_memories_count` | Jumlah memori di context window |
| `total_importance` | Total bobot memori aktif |
| `avg_importance` | Rata-rata relevansi |
| `section.memories_count` | Jumlah memori di benang merah |
| `descent_log_count` | Berapa kali memori diturunkan |

**Decision:**
- IF `active_memories_count` > 15: descend yang tidak relevan
- IF `avg_importance` < 0.5: lift memori yang lebih relevan
- IF `section.memories_count` == 0: tambah memori ke section

### 4.5 Reading `xanalyze` Output

| Field | Interpretasi |
|---|---|
| `memory_store_result.stored_count` | Jumlah findings yang disimpan ke memory |
| `memory_store_result.reused_count` | Findings identik yang memperbarui node lama |
| `memory_store_result.revised_count` | Logical finding sama dengan evidence/severity/hash baru |
| `memory_store_result.resolved_count` | Finding lama tidak ada pada analyzer snapshot lengkap kini |
| `memory_store_result.orphaned_count` | Source evidence tidak ada pada snapshot file kini |
| `memory_store_result.stale_count` | Analyzer gagal sehingga evidence lama belum tervalidasi pada snapshot kini |
| `memory_store_result.duplicate_input_count` | Evidence duplikat dalam batch yang dikuotienkan |
| `memory_store_result.batch_order_is_semantic_edge=false` | Urutan batch disimpan sebagai provenance event, bukan association semantic |
| `memory_store_result.provenance_event_records_added` | `1` untuk record detail baru; `0` bila batch steady-state dicoalesce |
| `memory_store_result.provenance_event_coalesced` | Run identik berturut-turut menambah `occurrence_count`, bukan panjang event list |
| `memory_store_result.provenance_event_records_compacted` | Record detail lama yang dipindahkan ke aggregate checkpoint pada transaksi ini |
| `memory_store_result.provenance_retention.hot_history_bounded` | Harus `true`; default maksimal 128 observation records |
| `memory_store_result.provenance_retention.archived_detail_recoverable` | Selalu `false`; archive mempertahankan count/digest, bukan payload lama |
| `memory_store_result.graph_content_signature` | Snapshot penuh yang menjadi dasar evidence |
| `consolidation_signal.consolidation_candidate` | Apakah perlu konsolidasi |
| `analysis_summary.health_score` | Kesehatan codebase |
| `analysis_summary.archetype` | Bentuk topologis codebase |

---

## 5. SAFETY CHECKS & INVARIANTS

### 5.1 Directed Reasoning-Cycle Safety (MUTLAK)

```
directed_reasoning_cycle_witness_count HARUS = 0 untuk safe bridge

JIKALAU directed_reasoning_cycle_witness_count > 0:
  → STOP operasi saat ini
  → Jalankan: memory betti_breakdown
  → Identifikasi directed witness
  → Hapus edge yang membentuk cycle (gunakan bridge --unsafe hanya jika perlu)

JIKALAU hanya β₁_reasoning > 0:
  → Audit reconvergence/diamond dan parallel association
  → JANGAN klaim circular reasoning tanpa directed witness
```

### 5.2 Cycle Prevention (Otomatis)

Bridge dengan `assoc_type="inferential"` atau `"causal"` akan **otomatis ditolak** jika membentuk cycle:
```json
{"status": "rejected", "reason": "would_create_reasoning_cycle"}
```
Command `memory associate` memakai directed reachability check yang sama untuk
tipe reasoning dan mengembalikan `error_code=would_create_reasoning_cycle`.
**JANGAN** override dengan `--unsafe` kecuali benar-benar diperlukan.

### 5.3 Fiber Compatibility (Otomatis)

Memori yang tidak punya tag overlap dengan fiber aktif akan **otomatis ditolak** saat lift:
```json
{"skipped_incompatible": N}
```
Ini mencegah confabulation (memori tidak konsisten masuk konteks).

### 5.4 Selective Filtering (xanalyze)

Hanya findings berikut yang disimpan ke memory:
- ✅ High severity findings
- ✅ Cross-analyzer correlations
- ✅ Critical medium findings (circular, entrypoint, change_risk)
- ❌ Low/info findings (transient, tidak disimpan)

### 5.5 Healthy Fragmentation

**TIDAK semua komponen perlu dihubungkan.** β₀ tinggi bisa jadi valid:
- `db_perf`, `ui_design` → healthy silos, biarkan terisolasi
- Bridge HANYA jika ada shared context meaningful
- JANGAN bridge antar domain yang tidak berhubungan (confabulation risk)

---

## 6. QUICK REFERENCE — CLI COMMANDS (`plw`)

Gunakan Native Command Layer (`plw`) untuk mencegah Context Bloat.

### Codebase Analysis (Zero-Bloat)
```bash
plw context "<query>" . --budget 1000
plw kan <file>
plw check
plw steer
plw impact <file>
plw brief <file>
```

### Memory Operations
```bash
plw memory store <episodic|semantic|procedural> "<content>" [--tags t1,t2] [--importance 0.8]
plw memory recall [--query q] [--type t] [--tags t1,t2] [--limit 20]
plw memory associate <from_id> <to_id> <type> [--strength 0.7]
plw memory consolidate <id1,id2,...> --content "<pattern>"
plw memory consolidate_auto
plw memory compact --consolidated
plw memory bridge <from> <to> [type]
```

### Memory Topology
```bash
hott_kernel.py memory analyze --output summary
hott_kernel.py memory analyze --include-historical --include-provenance --output summary  # audit only
hott_kernel.py memory steer --output summary
hott_kernel.py memory establish
hott_kernel.py memory drift
hott_kernel.py memory betti_breakdown
hott_kernel.py memory stats
```

`memory stats` adalah jalur inspeksi bounded provenance. Default policy menahan
128 record observation detail dan 256 namespace archive. Kebijakan ini hanya
berlaku pada `observation_batch`; consolidation event tetap exact karena
merupakan perubahan semantic yang eksplisit.

### Fiber Operations
```bash
plw fiber init "<task>" "<focus>"
plw fiber lift [--query q] [--max 10]
plw fiber descend --all
plw fiber status
```

### Cross-Domain
```bash
hott_kernel.py xanalyze src --output summary [--no-store]
hott_kernel.py xsteer src --output summary
hott_kernel.py xcontext <file>
```

### Tool Invocation Ergonomics & Self-Healing Contract
- **Interchangeable Parameter Aliases**: Argumen fleksibel dinormalisasi otomatis (misal `--target-file` / `--target-files` / `--targets`, `--budget-tokens` / `--budget_tokens`, `--max-hops` / `--max_hops`).
- **Self-Healing Error Diagnostics**: Jika dipanggil dengan mode yang salah atau tidak terdaftar, kernel mengembalikan error terstruktur `unknown_mode` beserta `valid_modes` dan `suggested_fix` tanpa melempar silent exception.
- **Anti-Churn Finding Identity**: `_stable_finding_subject` dihitung berbasis koordinat struktural (`analyzer`, `type`, `scope`), sehingga pembaruan teks observasi merevisi record yang ada (*in-place revision*) tanpa menciptakan duplikasi memori.

### Verification
```bash
python3 tools/ai_studio_tool/fixture_check.py
```

---

## 7. ARCHETYPE → STRATEGY MAPPING

### Codebase Archetypes

| Archetype | Strategy | Karakteristik |
|---|---|---|
| `tree_like` | hierarchical_traversal | Hirarkis, top-down aman |
| `modular` | isolated_analysis | Terfragmentasi, perubahan lokal |
| `sparse_cyclic` | cycle_aware_traversal | Ada cycles, waspada |
| `mixed_cyclic` | path_enumeration | Moderate cycles, petakan jalur |
| `dense_mesh` | conservative_edit | Sangat terhubung, hati-hati |
| `fragmented_sparse_cyclic` | component_localized_traversal | Terfragmentasi + cycles, isolasi per komponen |
| `fragmented_cyclic` | component_boundary_mapping | Petakan boundary komponen |

### Memory Archetypes

| Archetype | Strategy | Karakteristik |
|---|---|---|
| `memory_tree` | hierarchical_recall | Terintegrasi, recall mudah |
| `memory_modular` | isolated_exploration | Terfragmentasi, eksplorasi per klaster |
| `memory_sparse_cyclic` | cycle_aware_recall | Association cycle rank; cek witness sebelum menyebut loop |
| `memory_mixed_cyclic` | path_enumeration | Petakan association path dan arah edge |
| `memory_dense_mesh` | conservative_recall | Sangat terhubung, filtering ketat |
| `memory_fragmented_sparse_cyclic` | component_localized_recall | Reason per komponen; hubungkan hanya dengan witness |
| `memory_fragmented_cyclic` | component_mapping | Petakan komponen, validasi cross-component |

---

## 8. FILE STRUCTURE

`tools/ai_studio_tool/` adalah batas distribusi portabel. Angular/REST demo
berada di luar folder ini dan hanya boleh bergantung pada kernel, tidak sebaliknya.

```
tools/ai_studio_tool/
|- readme.md
|- skill.md
├── plw_cli.py                       # Zero-Bloat Native Command Layer (plw)
├── hott_kernel.py                   # Unified Kernel CLI & API Entrypoint
├── tools_schema.json                # JSON Tool Declarations
├── fixture_check.py                 # Self-contained portable regression
├── fixtures_min/                    # Minimal TS/JS invariant fixtures
│
├── core/                            # Shared Foundation (Layer 0)
│   ├── shared_graph.py              # Canonical graph representation
│   ├── graph_cache.py               # Persistent snapshot + incremental invalidation
│   ├── analyzer_cache.py            # Persistent evidence + signature invalidation
│   ├── analyzer_registry.py         # Registry & lifecycle management
│   ├── synthesizer.py               # Invariant encoder & decoder steering
│   ├── context_optimizer.py         # Query-directed quotient context + budget
│   ├── safety.py                    # Cycle prevention & Betti validation
│   ├── deprecation.py               # Standalone deprecation handlers
│   └── __init__.py                  # Core exports
│
├── data/codebase/cache/             # Source snapshots + analyzer evidence; Git-ignored
│
├── codebase/                        # Codebase Intelligence Domain (Layer 1)
│   ├── topology_analyzers.py        # Circular deps, risk evaluation
│   ├── performance_analyzers.py     # Async waterfall, deopt, GC, cache
│   ├── hott_analyzers.py            # Isomorphism, sheaf, homotopy, manifold
│   ├── targeted_queries.py          # Impact, outline, and brief queries
│   └── __init__.py                  # Codebase domain exports
│
├── memory/                          # Topological Memory Domain (Layer 2)
│   ├── store.py                     # CRUD, associations, retrieval
│   ├── runtime.py                   # Project scope, lock, atomic JSON, recovery
│   ├── retrieval.py                 # Single-snapshot inverted recall projection
│   ├── retrieval_cache.py           # Content-addressed recall cells + manifest
│   ├── provenance.py                # Bounded observation journal + checkpoint
│   ├── graph.py                     # Memory graph & adjacency builder
│   ├── analyzers.py                 # Memory fragmentation, hub, manifold, Betti
│   ├── betti.py                     # Edge-type-aware Betti breakdown
│   ├── consolidation.py             # Memory colimit & tag consolidation
│   ├── compact.py                   # Quotient forgetting & archiving
│   ├── bridge.py                    # Semantic bridging & homotopy extension
│   ├── synthesizer.py               # Memory steering, fingerprint, drift
│   ├── kan_extension.py             # Left (Lan) & Right (Ran) completions
│   └── __init__.py                  # Memory domain exports
│
├── context/                         # Fibration Context Window Domain (Layer 3)
│   ├── fibration.py                 # Fiber state lifecycle (init, lift, descend)
│   ├── section.py                   # Narrative section continuity
│   ├── transport.py                 # Parallel transport & decay factor
│   ├── compatibility.py             # Fiber-memory compatibility check
│   └── __init__.py                  # Context domain exports
│
├── bridge/                          # Cross-Domain Integration (Layer 4)
│   ├── xanalyze.py                  # Selective auto-store from code findings
│   ├── xsteer.py                    # Unified cross-domain steering
│   ├── xcontext.py                  # Memory-augmented file context
│   └── __init__.py                  # Bridge domain exports
│
├── data/runtime/scopes/             # Project-scoped memory/fiber state; Git-ignored
│
```

---

## 9. REST API ENDPOINTS

| Endpoint | Fungsi |
|---|---|
| `GET /api/topology` | Topology graph |
| `GET /api/impact?file=<path>` | Impact analysis |
| `GET /api/outline?file=<path>` | File outline |
| `GET /api/brief?file=<path>` | Brief (outline + impact) |
| `GET /api/async-detector?root=src` | Async anti-patterns |
| `GET /api/deopt-checker?root=src` | V8 deopt patterns |
| `GET /api/gc-pressure?root=src` | GC pressure |
| `GET /api/cache-auditor?root=src` | Cache audit |
| `GET /api/type-isomorphism?root=src` | Type isomorphism |
| `GET /api/boundary-sheaf?root=src` | Boundary sheaf |
| `GET /api/homotopy-paths?root=src` | Homotopy paths |
| `GET /api/topological-integrity?root=src` | Topological integrity |
| `GET /api/topological-manifold?root=src` | Manifold (Betti) |
| `GET /api/topological-fingerprint?root=src` | Fingerprint |
| `GET /api/decoder-steering?mode=steer&root=src` | Steering signals |

---

## 10. AGENT LOOP INTEGRATION

### Setiap Awal Sesi
```
1. hott_kernel.py xsteer src --output summary
2. BACA: drift, consolidation_candidate, archetype
3. IF drift != "none": establish baseline
4. IF consolidation_candidate: jalankan workflow 3.5
```

### Sebelum Edit File
```
1. hott_kernel.py context "<task>" src --target <file> --output prompt
2. hott_kernel.py brief <file> src --output summary  (jika perlu drill-down)
3. Baca blok `[PROJECT MEMORY EVIDENCE]` yang sudah dibudgetkan
4. hott_kernel.py xcontext <file> hanya jika perlu inspeksi memory lebih luas
5. Keputusan berdasarkan graph evidence + risk + memory context terverifikasi
```

### Setelah Perubahan Besar
```
1. hott_kernel.py xanalyze src --output summary
2. hott_kernel.py establish src
3. python3 tools/ai_studio_tool/fixture_check.py
4. IF consolidation_candidate: jalankan workflow 3.5
```

### Sebelum Akhir Sesi
```
1. hott_kernel.py fiber descend --all --reason "session_end"
2. hott_kernel.py memory steer --output summary
3. Simpan insight penting ke memory:
   hott_kernel.py memory store semantic "<insight>" --tags "session_learnings"
```
```

---
