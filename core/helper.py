import sys
sys.dont_write_bytecode =True

def print_colored(text, color):
    """
    Prints the given text in the specified color.

    Parameters:
    text (str): The text to be printed.
    color (str): The color to print the text in. Supported colors are:
                 'black', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white'
    """
    # ANSI escape codes for text colors
    colors = {
        'black': '\033[30m',
        'red': '\033[31m',
        'green': '\033[32m',
        'yellow': '\033[33m',
        'blue': '\033[34m',
        'magenta': '\033[35m',
        'cyan': '\033[36m',
        'white': '\033[37m',
        'orange': '\033[38;5;208m',
        'pink': '\033[38;5;205m',
        'purple': '\033[38;5;129m',
        'teal': '\033[38;5;37m',
        'olive': '\033[38;5;58m',
        'peach': '\033[38;5;216m',
        'beige': '\033[38;5;230m',
        'brown': '\033[38;5;94m',
    }

    # Reset code to revert to default color
    reset = '\033[0m'

    # Check if the specified color is supported
    if color in colors:
        print(colors[color] + text + reset)
    else:
        print("Unsupported color! Supported colors are:", ", ".join(colors.keys()))