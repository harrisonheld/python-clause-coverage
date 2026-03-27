from coverage_core import run_target_file


def print_report(runtime):
    print("\n==== Clause Coverage Report (CC) ====\n")

    covered = 0

    for cid in sorted(runtime.clause_data):
        data = runtime.clause_data[cid]
        expr = runtime.clause_meta[cid]

        true_seen = data["true"]
        false_seen = data["false"]

        full = true_seen and false_seen
        status = "FULL" if full else "PARTIAL"

        if full:
            covered += 1

        print(f"[Clause {cid}] {expr}")
        print(f"    True seen : {true_seen}")
        print(f"    False seen: {false_seen}")
        print(f"    Coverage  : {status}\n")

    total = len(runtime.clause_data)
    pct = (covered / total * 100) if total else 100.0

    print("--------------------------------")
    print(f"TCC Coverage: {covered}/{total} ({pct:.1f}%)")
    print("--------------------------------")


def run(filename):
    runtime = run_target_file(filename)
    print_report(runtime)