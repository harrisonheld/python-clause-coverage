from coverage_core import run_target_file


def _format_minor_context(runtime, minor_ctx):
    if not minor_ctx:
        return "<none>"

    parts = []
    for cid, value in minor_ctx:
        parts.append(f"{runtime.clause_meta[cid]}={value}")
    return ", ".join(parts)


def analyze_cacc(runtime):
    requirements = []

    for pid, predicate in runtime.predicate_meta.items():
        clauses = predicate["clauses"]
        predicate_events = [
            event for event in runtime.predicate_events if event["predicate_id"] == pid
        ]

        for major_cid in clauses:
            minor_cids = [cid for cid in clauses if cid != major_cid]
            seen_contexts = set()

            for event in predicate_events:
                values = event["clause_values"]

                if major_cid not in values:
                    continue
                if any(cid not in values for cid in minor_cids):
                    continue

                minor_ctx = tuple((cid, values[cid]) for cid in minor_cids)
                if minor_ctx in seen_contexts:
                    continue

                assignment_true = {cid: value for cid, value in minor_ctx}
                assignment_true[major_cid] = True
                assignment_false = {cid: value for cid, value in minor_ctx}
                assignment_false[major_cid] = False

                p_true = runtime.eval_predicate_logic(pid, assignment_true)
                p_false = runtime.eval_predicate_logic(pid, assignment_false)

                if p_true ^ p_false:
                    requirements.append(
                        {
                            "predicate_id": pid,
                            "major_cid": major_cid,
                            "minor_ctx": minor_ctx,
                            "expected": {True: p_true, False: p_false},
                        }
                    )
                    seen_contexts.add(minor_ctx)

    covered = 0
    for requirement in requirements:
        pid = requirement["predicate_id"]
        major_cid = requirement["major_cid"]
        expected = requirement["expected"]

        predicate_events = [
            event for event in runtime.predicate_events if event["predicate_id"] == pid
        ]

        true_side = any(
            major_cid in event["clause_values"]
            and event["clause_values"][major_cid] is True
            and event["predicate_value"] is expected[True]
            for event in predicate_events
        )
        false_side = any(
            major_cid in event["clause_values"]
            and event["clause_values"][major_cid] is False
            and event["predicate_value"] is expected[False]
            for event in predicate_events
        )

        requirement["observed"] = {True: true_side, False: false_side}
        requirement["satisfied"] = true_side and false_side

        if requirement["satisfied"]:
            covered += 1

    return requirements, covered


def run(filename):
    runtime = run_target_file(filename)
    requirements, covered = analyze_cacc(runtime)

    print("\n==== Correlated Active Clause Coverage (CACC) Report ====\n")
    total = len(requirements)
    pct = (covered / total * 100) if total else 100.0

    print(f"Requirements satisfied: {covered}/{total} ({pct:.1f}%)\n")

    if total == 0:
        print("No CACC requirements were generated from observed evaluations.")
        return

    for idx, requirement in enumerate(requirements, start=1):
        pid = requirement["predicate_id"]
        major_cid = requirement["major_cid"]
        minor_ctx = requirement["minor_ctx"]
        observed = requirement["observed"]
        status = "SAT" if requirement["satisfied"] else "UNSAT"

        print(f"[CACC-{idx}] {status}")
        print(f"    Predicate : {runtime.predicate_meta[pid]['expr']}")
        print(f"    Major     : {runtime.clause_meta[major_cid]}")
        print(f"    Seed minors context: {_format_minor_context(runtime, minor_ctx)}")
        print(f"    Found major=True with correlated p-value  : {observed[True]}")
        print(f"    Found major=False with correlated p-value : {observed[False]}\n")