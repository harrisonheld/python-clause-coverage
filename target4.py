# target4.py
def check(a: bool, b: bool) -> None:
    if (a or b):
        print("either")

check(True, False)   # short-circuits OR
check(False, True)   # both evaluated
check(False, False)  # both evaluated