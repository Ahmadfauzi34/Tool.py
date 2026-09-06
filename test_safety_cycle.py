import subprocess
import json
import sys

def run_plw(cmd):
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    try:
        return json.loads(res.stdout)
    except:
        print(f"Failed to parse JSON output for: {cmd}")
        print("Output:", res.stdout)
        print("Error:", res.stderr)
        sys.exit(1)

print("1. Membuat 3 node memori (A, B, C)...")
out_a = run_plw('plw memory store semantic "Premis A" --tags "test_loop"')
id_a = out_a["memory"]["id"]

out_b = run_plw('plw memory store semantic "Konklusi B (dari A)" --tags "test_loop"')
id_b = out_b["memory"]["id"]

out_c = run_plw('plw memory store semantic "Konklusi C (dari B)" --tags "test_loop"')
id_c = out_c["memory"]["id"]

print(f"   [OK] Terbuat: A={id_a[:8]}, B={id_b[:8]}, C={id_c[:8]}\n")

print("2. Menghubungkan A -> B (Valid: Penalaran Lurus)...")
res1 = run_plw(f'plw memory associate {id_a} {id_b} inferential')
print(f"   Status: {res1.get('status', 'OK')}")

print("\n3. Menghubungkan B -> C (Valid: Penalaran Lurus)...")
res2 = run_plw(f'plw memory associate {id_b} {id_c} inferential')
print(f"   Status: {res2.get('status', 'OK')}")

print("\n4. MENCOBA Menghubungkan C -> A (INVALID: Menciptakan Siklus Penalaran / Circular Reasoning)...")
# Menangkap output mentah karena ini diharapkan gagal
res3 = subprocess.run(f'plw memory associate {id_c} {id_a} inferential', shell=True, capture_output=True, text=True)
print("   [OUTPUT KERNEL MEMBLOKIR AKSI]:")
print(res3.stdout)

