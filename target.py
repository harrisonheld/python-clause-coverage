def check(a: int, b: int, c: list[int]) -> bool:
    if (a > 0 and b < 5):
        return True
    
    if (1 in c):
        return True
    
    return False


# The following two tests will provide a>0 true and false
# However, in check(-1, 6), the a>0 clause will be false
# Causing b<5 to not even be evaluated! 
# So you will not actually get b<5 totally covered unless it is truly evaluated as true AND false
check(1, 2, [])
check(-1, 6, [2, 3])