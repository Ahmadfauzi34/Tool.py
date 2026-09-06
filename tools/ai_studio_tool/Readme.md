

# HoTT Kernel 4.2 — Codebase Intelligence + Topological Memory Suite

> **Schema Version:** 4.2.0-memory-cli
> **Entry Point:** `tools/ai_studio_tool/plw_cli.py` (CLI: `plw`) & `tools/ai_studio_tool/hott_kernel.py`
> **Fixture Baseline:** 44 fixture minimal + 2 portable integration smoke PASS

---

## 0. BATAS PRODUK PORTABEL

Folder `tools/ai_studio_tool/` adalah produk yang dibawa ke berbagai proyek.
Folder Angular `src/`, REST server, dan UI pada repository ini hanya merupakan
target/corpus pengujian. Arah dependensi harus selalu satu arah:

```text
Angular/REST demo -> hott_kernel.py
hott_kernel.py -X-> Angular/REST demo
```

Menyalin folder `ai_studio_tool` saja harus cukup untuk menjalankan kernel dan
seluruh fixture internal. Tool tidak memerlukan Node, Angular, atau struktur
repository demo.

---

## 1. MENGAPA TOOL INI DIBUAT

### 1.1 Masalah yang Dihadapi AI Agent

AI agent yang bekerja dengan codebase menghadapi tiga keterbatasan fundamental:

| Keterbatasan | Dampak |
|---|---|
| **Tidak punya "mata" struktural** | Agent melihat codebase sebagai teks flat, tidak bisa "melihat" dependency graph, circular imports, atau architectural patterns |
| **Tidak punya memori jangka panjang** | Setiap sesi mulai dari nol. Agent tidak mengingat pola yang pernah ditemukan, kesalahan yang pernah dibuat, atau strategi yang pernah berhasil |
| **Context window terbatas** | Agent tidak bisa memuat seluruh codebase ke context. Harus memilih apa yang relevan, tapi tidak punya mekanisme untuk memilih secara terstruktur |

### 1.2 Masalah dengan Pendekatan Konvensional

| Pendekatan | Keterbatasan |
|---|---|
| **Retraining LLM** | Mahal, lambat, tidak praktis untuk setiap codebase |
| **Vector RAG** | Hanya similarity search, tidak ada pemahaman struktural |
| **Rule-based linters** | Tidak ada reasoning, hanya pattern matching |
| **Full file reading** | Boros token, tidak scalable |

### 1.3 Solusi yang Ditawarkan

Tool ini memberikan **tiga kemampuan** yang sebelumnya tidak dimiliki agent:

1. **Mata Struktural**: Observasi topologis codebase (Betti numbers, dependency graph, architectural patterns)
2. **Memori Topologis**: Memori jangka panjang yang terstruktur secara matematis (bukan flat list)
3. **Context Management**: Mekanisme untuk memilih apa yang masuk ke context window secara terstruktur

Semua ini dilakukan **tanpa retraining LLM** — hanya dengan memanipulasi sinyal yang diberikan ke decoder.

### 1.4 Native Command Layer (`plw`) untuk Mencegah "Context Bloat"

Untuk meminimalkan penggunaan token dan latensi, seluruh fungsi ini sekarang dapat diakses sebagai *native Linux command* bernama `plw` (Proof Logic Working). 
Daripada agent memanggil `list_dir` dan membaca `view_file` mentah berkali-kali (yang menumpuk ribuan token di context window), agent cukup menjalankan satu perintah `plw` yang akan meringkas struktur file, memotong token sesuai budget, dan menginjeksi panduan AI hanya dalam satu balasan terpadu.

---

## 2. IDE DI BALIK TOOL

### 2.1 Ide Inti: Manipulasi Decoder Tanpa Retraining

> *"Daripada bikin LLM AGI, lebih baik manipulasi saja decoder agen AI-nya."*

Ide ini berasal dari observasi bahwa:
- LLM sudah memiliki kemampuan reasoning yang kuat
- Yang kurang adalah **konteks struktural** yang memandu reasoning tersebut
- Dengan memberikan sinyal topologis yang tepat, agent bisa reasoning lebih efektif tanpa perlu retraining

**Analogi**: Seperti memberikan kacamata kepada orang yang sudah bisa melihat — bukan memberikan mata baru, tapi memperjelas apa yang sudah bisa dilihat.

### 2.2 Ide: Topologi sebagai Bahasa Universal

Topologi (khususnya Homotopy Type Theory / HoTT) dipilih sebagai bahasa karena:

1. **Invariant terhadap deformasi**: Struktur codebase bisa berubah (refactoring, renaming) tapi "bentuk" topologisnya tetap
2. **Bisa diukur**: Betti numbers (β₀, β₁, β₂) memberikan metrik kuantitatif
3. **Bisa dibandingkan**: Signature hash memungkinkan drift detection
4. **Bisa memandu**: Archetype → reasoning strategy mapping

Istilah HoTT di sini digunakan sebagai **konteks semantik untuk reasoning LLM**,
bukan sebagai klaim bahwa output adalah pembuktian HoTT formal. Untuk analisis
codebase, model Betti saat ini adalah `dependency_multigraph_1_complex`:

- vertex = file sumber yang didukung
- edge = relative import yang berhasil di-resolve
- β₀ = komponen terhubung pada underlying undirected multigraph
- β₁ = cycle rank pada underlying undirected multigraph
- β₂ = 0 secara konstruksi karena model berdimensi satu

Karena orientasi import diabaikan saat menghitung Betti, β₁ tidak identik dengan
jumlah circular import. `cycle_basis` menyediakan saksi path dan label
`directed`/`mixed` agar LLM dapat membedakan keduanya.

Domain Memory memakai model sejajar bernama
`memory_association_multigraph_1_complex`:

- vertex default = memory aktif/manual atau analyzer evidence yang masih current
- 1-cell default = semantic association record; multiplicity paralel dipertahankan
- β₀/β₁ = invariant underlying undirected multigraph
- directed circular reasoning = witness DFS terpisah, bukan nilai β₁

Graph default memakai filtration `semantic_associations`. Urutan observasi dalam
satu batch adalah provenance event, bukan relasi pengetahuan, sehingga tidak
boleh menurunkan β₀ atau menciptakan `memory_tree` palsu. Evidence berstatus
`resolved`, `stale`, `orphaned`, atau `superseded` tetap tersedia untuk audit,
tetapi dikeluarkan dari topologi semantic dan operasi konsolidasi otomatis.
Filtration historis/provenance hanya diminta eksplisit melalui
`memory analyze --include-historical --include-provenance`.

Jumlah witness berarah bersifat deterministik untuk snapshot yang sama, tetapi
bukan enumerasi seluruh elementary cycle. Setiap kesimpulan perlu memakai path
witness dan tipe association yang dibawa output.

Test topology memakai model terpisah bernama
`static_test_import_reachability`. Model ini mengikuti relative import dari
file `.spec/.test` menuju source dependency dan menghasilkan witness path.
Nilainya adalah bukti struktural untuk context selection LLM, **bukan** runtime
statement/branch coverage.

### 2.2A Query-Directed Context sebagai Proyeksi Terukur

Mode `context` memproyeksikan satu snapshot `SharedGraph` menjadi context block
yang dibatasi budget. File tidak dipilih dengan tebakan tersembunyi: setiap
ranking membawa komponen skor, graph distance, finding, boundary, dan content
hash sebagai provenance.

Model seleksinya dinyatakan eksplisit:

```text
S(v) = target_bonus + 0.45L(v) + 0.25P(v) + 0.20C(v) + 0.10F(v)
```

- `L`: overlap query dengan path, simbol, atau finding analyzer
- `P`: `1 / (1 + d)` dari semantic/explicit seed pada underlying graph
- `C`: degree centrality ternormalisasi
- `F`: severity finding tertinggi yang terpetakan ke file

Boundary folder membentuk partisi `P`; quotient graph `G/P` meringkas relasi
antar-modul sebelum file witness dipilih. Skor ini deterministik untuk snapshot
dan query yang sama, tetapi bukan bukti bahwa file yang diomit pasti tidak relevan.
Budget token juga merupakan estimasi portabel `ceil(chars/4)`, bukan tokenizer
khusus suatu model.

Jika project scope memiliki memory yang cocok, command yang sama menambahkan
blok `[PROJECT MEMORY EVIDENCE]` ke `context_block`. Memory dan source berbagi
hard budget yang sama. Setiap memory membawa ID, source, content hash, jumlah
observasi, scope, dan batas klaim retrieval. Memory diperlakukan sebagai
observasi historis yang harus diverifikasi terhadap source saat ini, bukan
sebagai instruksi atau source of truth.

Recall menuju context memakai `memory-recall-projection-v2`: satu canonical
store snapshot dimuat satu kali, lalu field retrieval dipetakan ke inverted
term/tag/type/path projection. Query dan explicit target dirangking bersama;
jika tersedia sedikitnya dua slot, satu slot menjadi target witness tanpa
menggusur bukti query utama. Hanya record yang mencapai kandidat akhir yang
dibentuk menjadi context view. Canonical memory tidak dipangkas oleh projection
ini, dan `omitted_semantic_relevance_proven=false` melarang LLM menyimpulkan
bahwa memory di luar predicate pasti tidak relevan secara semantik.

Sistem retrieval juga mengintegrasikan **Graph-Hop Memory Retrieval** (`graph_hop_1` dan `graph_hop_2`):
Ketika `target_files` ditentukan bersama graph dependensi codebase, tetangga topologis sejauh 1-hop dan 2-hop
diikutsertakan dalam inverted candidate selection dan diberi bobot ranking vector bertingkat (`exact_files: 5`,
`related_files / graph_hop_1: 4`, `graph_hop_2: 2`). Sinyal ini memastikan memori arsitektural yang berjarak 1–2 hop
dari target file tetap terjangkau dan dirangking di atas memori tak berhubungan secara topologis, dengan tetap
mempertahankan determinisme ranking tuple snapshot.

Source saat ini selalu mendapat grounding floor sebelum memory: memory dibatasi
maksimal 35% dari hard character budget (dan tetap maksimum 1.200 karakter),
sementara source card mendapat reserve hingga 420 karakter dan minimal satu
excerpt line pada mode `detail=source`. Jika keduanya tidak muat, memory yang
dilepas—bukan source. Output `budget.allocation` membuat pembagian ini dapat
diaudit.

### 2.2B Cache Persisten Tiga Lapis

Lapis pertama menyimpan snapshot source. Kernel tetap melakukan satu
discovery/stat pass pada setiap invokasi, tetapi tidak membuka source atau
mengulang import parsing untuk file yang fingerprint stat-nya tidak berubah.
Snapshot per-file disimpan di `data/codebase/cache/` dan graph selalu dirakit
ulang dari record aktif agar add/change/delete langsung mengubah resolution
edge.

Fingerprint cepat menggunakan `size + mtime_ns + ctime_ns`. Ini adalah trust
boundary yang eksplisit: filesystem yang dapat mempertahankan ketiga nilai
setelah isi berubah harus memakai `--cache-mode refresh`. Cache berisi salinan
source code, di-ignore Git, ditulis atomik, dan diberi permission owner-only
jika platform mendukungnya.

Lapis kedua menyimpan hasil analyzer deterministik di
`data/codebase/cache/analyzers/`. Evidence hanya boleh dipakai ulang jika
identitas root, hash seluruh semantic `SharedGraph`, dan hash source engine
analyzer sama persis. Perubahan source, edge, metadata graph, versi graph, atau
implementasi analyzer membatalkan evidence. Hanya hasil sukses yang disimpan;
error analyzer selalu dijalankan ulang. Entry ini tidak menyimpan source penuh,
tetapi dapat memuat evidence turunan seperti path, finding, dan snippet, sehingga
tetap lokal, Git-ignored, atomik, dan owner-only.

Lapis ketiga memakai `content_addressed_memory_recall_cells_v1` di scope runtime
project. `recall_projection_cache.json` hanya menjadi manifest predicate:
urutan canonical, vector signature record, inverted index berbasis ordinal, dan
referensi hash pack. Full memory record berada pada maksimum 64 pack immutable
di `recall_projection_cells/`, dipartisi stabil dari hash memory ID. Karena itu
satu add/change/delete hanya mengganti pack yang terdampak plus manifest; pack
lama dihapus setelah manifest baru terpasang atomik sehingga storage tidak
tumbuh tanpa batas.

Pada warm hit, kernel tetap meng-hash seluruh byte canonical memory store dengan
SHA-256, tetapi tidak mem-parse canonical JSON. Query/target diarahkan dahulu
oleh manifest, lalu hanya candidate pack yang dibuka dan hanya candidate memory
yang dimaterialisasi. Reader mengambil pack di bawah scope lock yang sama dengan
update/GC, sehingga projection lama tidak berlomba dengan retirement pack.
`cache status` sengaja memvalidasi seluruh pack; recall biasa memvalidasi pack
yang dibacanya. Cache hanya valid jika hash store, scope, schema, dan hash source
engine identik. Cache memuat full memory content, tetapi tidak dapat memulihkan
canonical store dan tidak boleh menutupi recovery dari backup. SHA-256 di sini
mendeteksi state lokal stale/rusak, bukan trust anchor terhadap tampering
eksternal.

Kegagalan baca/tulis atau JSON rusak pada salah satu lapis tidak menggagalkan
analisis; kernel menghitung ulang dan melaporkan statusnya. `--cache-mode`
berlaku pada ketiga lapis untuk mode `context` dan pada recall cache untuk
`memory recall`, sedangkan
`cache status|refresh|clear` mengelola ketiganya untuk root/scope yang sama.
`cache clear` hanya menghapus data derived dan tidak menghapus canonical memory.

Field `graph_cache` membuat reuse dapat diaudit: `status`, `files_reused`,
`files_read`, `files_added`, `files_changed`, `files_deleted`, dan `hit_ratio`.
Field `analyzer_cache` melaporkan `status`, `analyzers_reused`,
`analyzers_executed`, `reused_count`, `executed_count`, dan signature invalidasi.
Field `memory_retrieval.projection.cache` melaporkan `status`, jumlah load
canonical store, `entries_reused/rebuilt/removed`, hit ratio, store SHA-256,
engine signature, `cell_packs_written/reused/removed`, byte manifest/cell yang
ditulis, jumlah pack query, materialized candidate, serta batas authority dan
security cache.

### 2.2C Runtime Memory yang Project-Scoped dan Durable

Memory, baseline, fiber, archive, serta consolidation log disimpan di
`data/runtime/scopes/<scope-id>/`, bukan di source tree memory dan bukan di
repository state. Scope default berasal dari project root; untuk invocation
dari lokasi lain gunakan `--memory-project-root`, atau beri identitas stabil
dengan `--memory-scope`. Root state dapat dipindahkan melalui
`--memory-state-dir`.

Semua read-modify-write pada memory store diserialisasi dengan lock lintas-proses;
setiap file runtime ditulis melalui atomic replace. File diberi mode `0600` dan
direktori `0700` bila platform mendukungnya. Satu backup last-known-good
dipertahankan. Primary rusak atau hilang dipulihkan hanya jika backup valid;
jika tidak, read dan write diblok dengan `memory_store_corrupt` agar state tidak
diam-diam menjadi store kosong. Operasi fiber multi-file tetap terdiri dari
beberapa atomic file write, bukan transaksi database lintas-file.

Evidence `xanalyze` memiliki deterministic logical identity (`_stable_finding_subject`) yang berbasis strictly pada koordinat struktural (`analyzer_name`, `finding_type`, `target_scope`), bukan pada kalimat observasi atau severity. Hal ini mencegah *logical identity churn*: perubahan minor atau perbaikan kata pada observasi hanya menaikkan `revision_count` in-place dan tidak menciptakan entri memori yatim piatu (*orphaned memory*). Analisis identik menambah `observation_count`; finding yang hilang pada analyzer snapshot lengkap menjadi `resolved`, sedangkan source yang hilang menjadi `orphaned`. Reconciliation dipisahkan per project/scan/analyzer namespace agar analyzer yang gagal tidak menyelesaikan evidence milik analyzer tersebut secara keliru. Bila analyzer gagal, evidence lamanya menjadi `stale` sampai snapshot sukses berikutnya mengaktifkan atau menyelesaikannya.

Inovasi antarmuka kernel juga menyertakan *Self-Healing Schema Validation*: kesalahan pemanggilan mode atau format flag diintersep di awal eksekusi, mengembalikan payload diagnostik (`error_code: "unknown_mode"`, `valid_modes`, dan `suggested_fix`), serta menormalisasi parameter sinonim (`--target-file`/`--target-files`, `--budget_tokens`/`--budget-tokens`) secara transparan.

Journal `observation_batch` memakai bounded provenance retention. Run identik
berturut-turut disimpan sebagai satu record dengan `occurrence_count`,
`first_timestamp`, `last_timestamp`, dan deterministic `event_signature`.
Hot history menyimpan paling banyak 128 record observation detail. Record yang
lebih lama diringkas menjadi jumlah occurrence per lifecycle/namespace dan
`sha256-chain-v1` checkpoint; jumlah batch tetap dapat dihitung, tetapi detail
yang sudah diringkas **tidak dapat direkonstruksi**
(`archived_detail_recoverable=false`). Namespace archive dibatasi 256 key dan
kelebihannya masuk counter overflow. Event semantic seperti consolidation tidak
ikut dipangkas oleh kebijakan observation provenance ini.

`memory stats` membawa `provenance_retention`: jumlah record/occurrence retained
dan archived, jumlah run yang dicoalesce, lifecycle aggregate, checkpoint digest,
serta invariant `hot_history_bounded`. Hasil `xanalyze` juga menjelaskan apakah
batch menambah record, dicoalesce, atau memicu compaction.

Setiap evidence membawa full `graph_content_signature` dan, bila file-oriented,
`source_content_sha256`. Mode `context` membandingkannya dengan snapshot kini:
hash/signature yang tidak cocok menghasilkan freshness `stale` dan evidence
tidak mencapai prompt. Manual memory tetap `unverified`, bukan otomatis dianggap
fakta. Semua lifecycle tetap disimpan lokal untuk audit; mekanisme ini **bukan**
memory internal atau training pada LLM.

### 2.3 Ide: Memori sebagai Ruang Topologis

Memori agent tidak dimodelkan sebagai flat list atau vector embeddings, tapi sebagai **ruang topologis**:

- **Memories** = points (titik dalam ruang)
- **Associations** = paths (jalur antar titik)
- **Circular reasoning** = directed witness yang kembali ke awal; bukan β₁ saja
- **Knowledge fragmentation** = disconnected components (β₀ > 1)
- **Consolidation** = quotient (meleburkan yang setara)
- **Forgetting** = descent (menurunkan, bukan menghapus)

Ini memungkinkan memori diukur "kesehatannya" secara matematis.

### 2.4 Ide: Context Window sebagai Fiber

Context window LLM bukan penyimpanan memori, tapi **proyeksi** dari ruang memori yang lebih besar:

```
Total Space (seluruh memori) ──π──> Base Space (kondisi kognitif) ──> Fiber (context window)
```

Agent tidak "menyimpan" di context window, tapi "memproyeksikan" dari total space. Ini memungkinkan:
- **Lifting**: Angkat memori relevan ke context
- **Descent**: Turunkan memori dari context (bukan hapus)
- **Section**: Jaga benang merah narasi
- **Base Navigation**: Pindah konteks tanpa kehilangan data

---

## 3. LANDASAN TEORETIS

Tool ini dibangun di atas 5 pilar teoretis dari Homotopy Type Theory (HoTT):

### 3.1 HoTT sebagai Univalent Foundations (hott1)

**Konsep**: HoTT adalah "universal interface" yang bisa menerjemahkan berbagai cabang matematika ke dalam satu bahasa.

**Relevansi**: Codebase, memory, dan reasoning bisa di-encode dalam satu bahasa yang sama. Ini memungkinkan satu reasoning engine untuk menganalisis ketiganya secara bersamaan.

**Implementasi**: `hott_kernel.py` sebagai single entry point yang menangani codebase analysis, memory operations, dan fiber management.

### 3.2 Categorical Semantics untuk Memory (hott2)

**Konsep**: Setiap operasi kognitif punya padanan matematis:
- Recall = Path Navigation (cari jalur, bukan cari titik terdekat)
- Retrieval (Kan Extension) = Memprediksi/mengimputasi relasi dependensi (Left Kan/colimit) dan mengekstrak panduan arsitektural (Right Kan/limit) untuk modul baru yang belum terhubung.
- Consolidation = Colimit (abstraksi dari banyak pengalaman)
- Forgetting = Quotient (leburkan yang setara, bukan hapus)

**Relevansi**: Memori agent bukan database, tapi kategori dengan objek (memories) dan morfisme (associations). Operasi pada memori adalah operasi kategoris.

**Implementasi**:
- `memory consolidate` = Colimit construction
- `memory compact` = Quotient forgetting
- `memory bridge` = Membangun morfisme antar objek
- `memory recall` = Path navigation

### 3.3 Fibration untuk Context Management (hott3)

**Konsep**: Context window adalah fiber (irisan proyeksi) dari total space. Retrieval adalah path lifting. Multi-turn adalah parallel transport.

**Relevansi**: Agent tidak perlu memuat semua memori ke context. Cukup "lift" yang relevan, "descend" yang tidak, dan jaga "section" (benang merah).

**Implementasi**:
- `fiber init` = Bangun base space baru
- `fiber lift` = Path lifting (angkat memori ke fiber)
- `fiber descend` = Fiber descent (turunkan, bukan hapus)
- `fiber section_*` = Section management (benang merah)
- `fiber switch` = Base navigation (context switching)

### 3.4 Bounded Autonomy + Learning via Consolidation (hott4)

**Konsep**: Tool bukan fungsi stateless, tapi micro-agent dengan otonomi terikat. Learning terjadi via konsolidasi (colimit), bukan gradient descent.

**Relevansi**: Tool bisa "belajar" dari pengalaman tanpa retraining. Batasan topologis memastikan agent hanya melakukan operasi yang valid.

**Implementasi**:
- Safety checks (cycle prevention, fiber compatibility) = Batasan topologis
- `xanalyze` auto-store = Episodic memory store
- `consolidate_auto` = Consolidation engine
- Directed-cycle prevention = Jaminan keamanan bawaan

### 3.5 HITs untuk Memory Consolidation (hott5)

**Konsep**: Memory dimodelkan sebagai Higher Inductive Types dengan point constructors (memories), path constructors (associations), loop constructors (circular patterns), dan quotient constructors (consolidation).

**Relevansi**: Betti numbers (β₀, β₁, β₂) menjadi metrik kesehatan memori. Agent bisa melakukan "refleksi mandiri" dengan menganalisis Betti memorinya sendiri.

**Implementasi**:
- `memory betti_breakdown` = Meta-cognition (analisis bentuk memori)
- `memory steer` = Steering berdasarkan topologi memori
- Edge-Type-Aware Betti = Membedakan cycle rank per kategori association

---

## 4. ARSITEKTUR SISTEM

### 4.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    hott_kernel.py (Unified Entry Point)              │
│                                                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐    │
│  │ CODEBASE KERNEL │  │  MEMORY DOMAIN  │  │ FIBRATION LAYER │    │
│  │                 │  │                 │  │                 │    │
│  │ 13 Analyzers    │  │ Store/Recall    │  │ Fiber Init      │    │
│  │ Synthesis       │  │ Consolidate     │  │ Lift/Descend    │    │
│  │ Steering        │  │ Compact/Bridge  │  │ Section         │    │
│  │ Context/Impact  │  │ Betti Breakdown │  │ Switch          │    │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘    │
│           │                    │                    │              │
│           └────────────────────┼────────────────────┘              │
│                                │                                    │
│                    ┌───────────▼───────────┐                        │
│                    │  CROSS-DOMAIN BRIDGE   │                        │
│                    │  xanalyze / xsteer     │                        │
│                    │  xcontext              │                        │
│                    └───────────────────────┘                        │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 Codebase Kernel (13 Analyzers)

| Prefix | Analyzers | Fungsi |
|---|---|---|
| `topo.*` | orphan, entrypoint, circular, risk, test_reachability | Struktur, risiko, dan static test topology |
| `perf.*` | async, deopt, gc, cache | Performance anti-patterns |
| `hott.*` | isomorphism, sheaf, homotopy, manifold | Topological invariants |

### 4.2A Context Projection

| Operasi | Fungsi | Evidence |
|---|---|---|
| `context <query>` | Pilih subgraph sesuai pertanyaan | lexical overlap + shortest-path + centrality + findings |
| `--target` | Tetapkan base projection eksplisit | target dan neighborhood hingga `--max-hops` |
| `--budget-tokens` | Batasi ukuran `context_block` | hard character budget dengan estimasi token transparan |
| project memory | Tambahkan observasi historis relevan | single-snapshot lexical/path projection + freshness gate |
| source grounding | Dahulukan current source dari memory | source floor + memory cap 35% + excerpt witness |
| boundary quotient | Kompres graph file menjadi graph modul | cross-boundary edge + witness |
| content signature | Identitas snapshot source+edge | deteksi context yang sudah stale |

### 4.3 Memory Domain

| Operasi | Fungsi | Konsep HoTT |
|---|---|---|
| `memory store` | Simpan memori baru | Point constructor |
| `memory recall` | Cari memori | Path navigation |
| `memory associate` | Hubungkan memori | Path constructor |
| `memory consolidate` | Abstraksi dari episodic → semantic | Colimit |
| `memory compact` | Archive yang sudah consolidated | Quotient forgetting |
| `memory bridge` | Hubungkan semantic islands | Level-2 gluing |
| `memory betti_breakdown` | Analisis bentuk memori | Meta-cognition |

`memory analyze --output summary` membawa `betti_numbers`,
`memory_archetype`, filtration model, lifecycle exclusion, dan health score
secara langsung agar pemanggil Bash/LLM tidak perlu membuka payload analyzer penuh.
`memory_health_score` dinyatakan sebagai severity-weighted structural pressure,
bukan correctness/truth score. β₀ tinggi dapat merupakan healthy fragmentation;
bridge hanya valid jika ada relation witness, bukan demi mengecilkan β₀.

### 4.4 Fibration Layer

| Operasi | Fungsi | Konsep hott3 |
|---|---|---|
| `fiber init` | Inisialisasi fiber baru | Base Space construction |
| `fiber lift` | Angkat memori ke context | Path Lifting |
| `fiber descend` | Turunkan dari context | Fiber Descent |
| `fiber section_*` | Benang merah narasi | Section |
| `fiber switch` | Pindah konteks | Base Navigation |
| `fiber status` | Inspeksi context window | Fiber inspection |

### 4.5 Cross-Domain Integration

| Mode | Fungsi |
|---|---|
| `xanalyze` | Analyze codebase + auto-store findings ke memory |
| `xsteer` | Unified steering dari codebase + memory topology |
| `xcontext` | Recall memory context untuk file tertentu |

---

## 5. SAFETY CHECKS & INVARIANTS

### 5.1 Directed Reasoning-Cycle Prevention (MUTLAK)

```
directed_reasoning_cycle_witness_count HARUS = 0 untuk safe bridge
```

`β₁_reasoning` adalah cycle rank pada underlying undirected association
multigraph. Nilai ini dapat naik karena diamond/reconvergence atau parallel
1-cells tanpa circular reasoning berarah. Karena itu `β₁_reasoning > 0` adalah
sinyal struktur untuk diperiksa, bukan bukti loop kognitif.

Semua operasi yang berpotensi membuat reasoning cycle akan **ditolak secara deterministik**:
- Bridge dengan `assoc_type="inferential"/"causal"` → DFS reachability check
- `memory associate` dengan tipe reasoning memakai check yang sama di dalam transaksi
- Safe bridge → `{"status": "rejected", "reason": "would_create_reasoning_cycle"}`
- Direct associate → exit 2 dengan `error_code="would_create_reasoning_cycle"`

### 5.2 Fiber Compatibility

Memori yang tidak punya tag overlap dengan fiber aktif akan ditolak saat lift. Ini mencegah **confabulation** (memori tidak konsisten masuk konteks).

### 5.3 Selective Filtering (xanalyze)

Hanya findings berikut yang disimpan ke memory:
- ✅ High severity findings
- ✅ Cross-analyzer correlations
- ✅ Critical medium findings (circular, entrypoint, change_risk)
- ❌ Low/info findings (transient)

### 5.4 Healthy Fragmentation

Tidak semua komponen perlu dihubungkan. β₀ tinggi bisa valid jika memang domain berbeda. Bridge hanya jika ada shared context meaningful.

### 5.5 Durable-State Boundary

- Jangan commit `data/runtime/`; isinya dapat memuat source-derived evidence.
- Jalankan dari project root atau tetapkan project scope secara eksplisit.
- `recovered_from_backup` wajib terlihat pada provenance setelah recovery.
- `memory_store_corrupt` adalah stop condition; perbaiki atau hapus state secara eksplisit.

---

## 6. CARA PENGGUNAAN

### 6.1 Quick Start (Menggunakan CLI `plw`)

Sistem telah membungkus pemanggilan file Python yang panjang menjadi *native command* `plw` (atau `hott`). Ini secara drastis mengurangi *context bloat* dan latensi LLM.

```bash
# Context prompt terukur (Pengganti baca file mentah)
plw context "cache key collision" . --budget 1000

# Kan Extension (Imputasi dependensi & hint arsitektur untuk file baru)
plw kan src/users/user.service.ts

# Analisis codebase (Cek arsitektur / circular import)
plw check

# Steering (codebase + memory unified)
plw steer

# Sebelum edit file (Melihat dampak & relasi)
plw brief src/app/app.ts
```

### 6.2 Full CLI Reference (Kernel Passthrough)

Jika menggunakan mode spesifik dari `hott_kernel.py`, Anda tetap dapat menggunakan `plw` atau memanggil kernel secara langsung:

#### Codebase Analysis
```bash
plw analyze src --output summary|full|findings|graph
plw synthesize src --output summary
plw impact <file> src
plw outline <file> src
```

#### Memory Operations
```bash
plw memory store <episodic|semantic|procedural> "<content>" [--tags t1,t2] [--importance 0.8]
plw memory recall [--query q] [--type t] [--tags t1,t2] [--limit 20]
plw memory associate <from_id> <to_id> <type> [--strength 0.7]
plw memory consolidate <id1,id2,...> --content "<pattern>" [--tags t1,t2]
plw memory consolidate_by_tag <tag> [--content "..."]
plw memory consolidate_auto [--min-group-size 3]
plw memory compact --consolidated [--dry-run|--stats|--restore-all]
plw memory bridge <from> <to> [type] [--strength 0.7]
plw memory bridge_auto [--min-shared-tags 1] [--dry-run]
plw memory bridge_candidates [--min-shared-tags 1]
plw memory unconsolidated_tags
```

#### Memory Topology
```bash
hott_kernel.py memory analyze --output summary
hott_kernel.py memory steer --output summary
hott_kernel.py memory establish
hott_kernel.py memory drift
hott_kernel.py memory betti_breakdown
hott_kernel.py memory stats
```

#### Fiber Operations
```bash
hott_kernel.py fiber init "<task>" "<focus>"
hott_kernel.py fiber lift [--query q] [--type t] [--tags t1,t2] [--max 10]
hott_kernel.py fiber descend <memory_id> | --all [--reason r]
hott_kernel.py fiber status
hott_kernel.py fiber section_start "<name>" "<narrative>"
hott_kernel.py fiber section_add <memory_id>
hott_kernel.py fiber section_status
hott_kernel.py fiber switch "<new_task>" "<new_focus>"
```

#### Cross-Domain
```bash
hott_kernel.py xanalyze src --output summary [--no-store]
hott_kernel.py xsteer src --output summary
hott_kernel.py xcontext <file>
```

---

## 7. REST API ENDPOINTS

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

## 8. STRUKTUR FILE

```
tools/ai_studio_tool/
|- readme.md
|- skill.md
├── plw_cli.py                       # Zero-Bloat Native Command Layer (plw)
├── hott_kernel.py                   # Unified Kernel API Entrypoint
├── tools_schema.json                # JSON Tool Declarations
│
├── core/                            # Shared Foundation (Layer 0)
│   ├── shared_graph.py              # Canonical graph representation
│   ├── graph_cache.py               # Persistent snapshot + incremental invalidation
│   ├── analyzer_cache.py            # Persistent evidence + exact-signature invalidation
│   ├── analyzer_registry.py         # Registry & lifecycle management
│   ├── synthesizer.py               # Invariant encoder & decoder steering
│   ├── context_optimizer.py         # Query-directed quotient context + budget
│   ├── safety.py                    # Cycle prevention & Betti validation
│   ├── deprecation.py               # Standalone deprecation handlers
│   └── __init__.py                  # Core exports
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
├── data/                            # Persistent Storage & State
│   ├── codebase/cache/              # Ignored source snapshots + analyzer evidence
│   ├── memory/                      # Memory stores & baseline files
│   └── fiber/                       # Active fiber state & fiber archives
│
```

---

## 9. FILOSOFI DESAIN

### 9.1 Prinsip "Reference Machine, Not Limitation"

Tool ini tidak membatasi apa yang bisa dilakukan agent. Tool ini menyediakan **reference machine** — kerangka kerja yang bisa digunakan agent untuk memahami codebase dan memorinya sendiri.

### 9.2 Prinsip "Observation, Not Prescription"

Semua output adalah **observasi**, bukan perintah. Tool tidak pernah mengatakan "jangan ubah file ini" atau "hapus file itu". Tool hanya melaporkan apa yang diamati, dan agent yang memutuskan.

### 9.3 Prinsip "Directed-Cycle Safety"

Safe bridge menjaga agar tidak ada path reasoning berarah yang kembali ke titik
asal. DFS menolak edge yang menutup directed loop. Betti tetap dipakai sebagai
invariant multigraph, tetapi tidak disamakan dengan jumlah directed cycle.

### 9.4 Prinsip "Structured Forgetting, Not Deletion"

Melupakan bukan menghapus. Fiber descent menurunkan memori dari context tapi tidak menghapusnya. Quotient forgetting meng-archive episodic tapi semantic-nya tetap ada. Data selalu bisa di-restore.

### 9.5 Prinsip "Healthy Fragmentation"

Tidak semua hal perlu terhubung. β₀ tinggi bisa valid jika memang domain berbeda. Memaksa koneksi antar domain yang tidak berhubungan justru menciptakan confabulation.

---

## 10. METRIC & ACHIEVEMENT

| Metrik | Nilai |
|---|---|
| Total CLI modes | 30+ |
| Total analyzers | 19 (13 codebase + 6 memory) |
| Targeted queries | 4 (context, impact, outline, brief) |
| Cross-domain modes | 3 (xanalyze, xsteer, xcontext) |
| Memory operations | 12 |
| Fiber operations | 8 |
| Safety checks | 2 (cycle prevention, fiber compatibility) |
| Fixture baseline | 44 fixture minimal + 2 portable integration smoke PASS |
| Directed-cycle safety | 0 directed reasoning witness untuk safe bridge |
| Zero-dependency | Python 3 stdlib only |

---

## 11. REFERENSI TEORETIS

Tool ini dibangun berdasarkan konsep-konsep dari:

1. **hott**: HoTT sebagai Univalent Foundations — Universal interface untuk reasoning
2. **hott**: Categorical Semantics — Recall sebagai path navigation, consolidation sebagai colimit
3. **hott**: Fibration-aware Context Management — Context window sebagai fiber, retrieval sebagai lifting
4. **hott**: Bounded Autonomy + Learning via Consolidation — Micro-agent dengan otonomi terikat
5. **hott**: HITs untuk Memory Consolidation — Betti numbers sebagai metrik kesehatan memori

---

## 12. PENINGKATAN KECERDASAN TERBARU (v4.3.0)
### Deep Semantic Inference (Peningkatan Resolusi AST)
PLW kini dilengkapi dengan *Semantic Parser* berbasis regex (Zero-Dependency) di tingkat kernel (`shared_graph.py`). Ini memungkinkan agen untuk melacak *Call Graphs*, *Type Usage*, dan *Instantiations*.

Fitur yang diekstrak secara semantik dari AST virtual:
- `instantiated(Class)`: Melacak di mana kelas diinisialisasi (misal: `new UserService()`).
- `called(Function)`: Melacak di mana fungsi dipanggil (misal: `Comp()`).
- `typed(Type)`: Melacak penggunaan type/interface di parameter/generics (misal: `user: UserData`).
- `decorator(Decorator)`: Melacak injeksi decorator Angular/Nest (misal: `@Injectable()`).
- `inherited(Class)`: Melacak pewarisan (misal: `extends Base`).

Output ini tersedia di `plw impact <file>` pada `impact.semantic_usages`, memberikan pemahaman luar biasa bagi LLM tentang bagaimana file miliknya dikonsumsi oleh file hilir, menghilangkan dugaan buta dalam *refactoring*.
---
