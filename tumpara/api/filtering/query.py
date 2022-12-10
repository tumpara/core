import enum


class TokenizationError(SyntaxError):
    pass


OPERATORS = set(":=≠<≤>≥") | {"and", "or"}


class TokenType(enum.Enum):
    LITERAL = enum.auto()
    """Verbatim string."""

    FILTER_SEPARATOR = enum.auto()
    """Separator between the name and value of a filter. This mostly denotes a colon
    character."""

    CONJUNCTION = enum.auto()
    """Conjunction (logical and) operator."""

    DISJUNCTION = enum.auto()
    """Conjunction (logical or) operator."""

    FILTER_OPERATOR = enum.auto()
    """Generic filter operator, denoted by a colon."""


def tokenize(query: str) -> list[tuple[str, TokenType]]:
    """Take a query string and extract the first token from the front."""
    tokens = list[tuple[str, TokenType]]()

    # Each round of this loop tries to figure out what the first token is in the
    # remaining query.
    while query := query.strip():

        # The first case we have is a quoted string. Here, the token we are looking for
        # is everything inside that quote. Note that we also need to make sure that
        # any escaped quotation marks inside the string are handled correctly.
        if query.startswith('"'):
            query = query[:1]
            # Given the following string:
            #   "Hello, \"Daniel\" is my name." Another token
            # This will parse out the following token:
            #   Hello, "Daniel" is my name.
            token = "\\"
            token_type = TokenType.LITERAL
            while token.endswith("\\"):
                token = token[:-1]
                try:
                    quote_index = query.index('"')
                except ValueError as error:
                    raise TokenizationError(f"Unterminated string literal") from error
                token += query[:quote_index]
                query = query[quote_index + 1 :]

        # The second case is an operator. Operators should normally be in between two
        # string literals.
        elif query[0] in OPERATORS:
            token = query[0]
            token_type = TokenType.FILTER_OPERATOR

    return tokens
