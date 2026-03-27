def check(a: int, b: bool) -> None:
    if (a > 0 and b):
        print('Howdy')

    if (a == 10 and b):
        print("Meowdy")


check(5, True)
check(10, True)
check(-10, False)
check(5, False)
check(10, False)