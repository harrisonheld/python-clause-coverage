from coverage_core import run_target_file


def _format_minor_context(runtime, minor_ctx):
    if not minor_ctx:
        return "<none>"

    parts = []
    for cid, value in minor_ctx:
        parts.append(f"{runtime.clause_meta[cid]}={value}")
    return ", ".join(parts)


def _find_events_for_context(events, major_cid, minor_ctx):
    matches = []

    for event in events:
        values = event["clause_values"]
        if major_cid not in values:
            continue

        ok = True
        for cid, expected in minor_ctx:
            if cid not in values or values[cid] != expected:
                ok = False
                break

        if ok:
            matches.append(event)

    return matches


def _is_masked_by_short_circuit(events, major_cid, major_value, minor_ctx):
    for event in events:
        values = event["clause_values"]
        if major_cid not in values or values[major_cid] is not major_value:
            continue

        compatible = True
        missing_minor = False

        for cid, expected in minor_ctx:
            if cid not in values:
                missing_minor = True
                continue

            if values[cid] != expected:
                compatible = False
                break

        if compatible and missing_minor:
            return True

    return False


def analyze_racc(runtime):
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
    masked = 0
    for requirement in requirements:
        pid = requirement["predicate_id"]
        major_cid = requirement["major_cid"]
        minor_ctx = requirement["minor_ctx"]
        expected = requirement["expected"]

        predicate_events = [
            event for event in runtime.predicate_events if event["predicate_id"] == pid
        ]
        matches = _find_events_for_context(predicate_events, major_cid, minor_ctx)

        true_side = any(
            event["clause_values"][major_cid] is True
            and event["predicate_value"] is expected[True]
            for event in matches
        )
        false_side = any(
            event["clause_values"][major_cid] is False
            and event["predicate_value"] is expected[False]
            for event in matches
        )

        requirement["observed"] = {
            True: any(event["clause_values"][major_cid] is True for event in matches),
            False: any(event["clause_values"][major_cid] is False for event in matches),
        }
        requirement["satisfied"] = true_side and false_side

        masked_true = False
        masked_false = False

        if not true_side:
            masked_true = _is_masked_by_short_circuit(
                predicate_events, major_cid, True, minor_ctx
            )

        if not false_side:
            masked_false = _is_masked_by_short_circuit(
                predicate_events, major_cid, False, minor_ctx
            )

        requirement["masked"] = {True: masked_true, False: masked_false}
        requirement["masked_by_short_circuit"] = (
            (not requirement["satisfied"]) and (masked_true or masked_false)
        )

        if requirement["satisfied"]:
            covered += 1
        elif requirement["masked_by_short_circuit"]:
            masked += 1

    return requirements, covered, masked


def run(filename):
    runtime = run_target_file(filename)
    requirements, covered, masked = analyze_racc(runtime)

    print("\n==== Restricted Active Clause Coverage (RACC) Report ====\n")
    total = len(requirements)
    pct = (covered / total * 100) if total else 100.0

    print(f"Requirements satisfied: {covered}/{total} ({pct:.1f}%)\n")
    if masked:
        print(f"Short-circuit masked requirements: {masked}/{total}\n")

    if total == 0:
        print("No RACC requirements were generated from observed evaluations.")
        return

    for idx, requirement in enumerate(requirements, start=1):
        pid = requirement["predicate_id"]
        major_cid = requirement["major_cid"]
        minor_ctx = requirement["minor_ctx"]
        observed = requirement["observed"]
        masked_info = requirement["masked"]

        if requirement["satisfied"]:
            status = "SAT"
        elif requirement["masked_by_short_circuit"]:
            status = "MASKED"
        else:
            status = "UNSAT"

        print(f"[RACC-{idx}] {status}")
        print(f"    Predicate : {runtime.predicate_meta[pid]['expr']}")
        print(f"    Major     : {runtime.clause_meta[major_cid]}")
        print(f"    Minors    : {_format_minor_context(runtime, minor_ctx)}")
        print(f"    Observed major=True  : {observed[True]}")
        print(f"    Observed major=False : {observed[False]}\n")

        if status == "MASKED":
            print(
                f"    Masked major=True side by short-circuit  : {masked_info[True]}"
            )
            print(
                f"    Masked major=False side by short-circuit : {masked_info[False]}\n"
            )