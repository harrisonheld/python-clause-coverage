def check(a: int, b: int, c: list[int]) -> bool:
    if (a > 0 and b < 5):
        return True
    
    if (1 in c):
        return True
    
    return False


check(1, 2, [])
check(-1, 2, [1])
check(-1, 6, [2, 3])
check(2, 6, [])