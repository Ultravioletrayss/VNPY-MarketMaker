def greet(name):
    return f"Hello, {name}! Welcome to Python."


def calculate_total(numbers):
    return sum(numbers)


def main():
    name = input("What is your name? ").strip()

    if not name:
        name = "friend"

    scores = [85, 92, 78]
    total = calculate_total(scores)
    average = total / len(scores)

    print(greet(name))
    print(f"Scores: {scores}")
    print(f"Total: {total}")
    print(f"Average: {average:.2f}")


if __name__ == "__main__":
    main()
