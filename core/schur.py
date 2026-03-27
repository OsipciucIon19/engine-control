from __future__ import annotations

import math
from typing import List, Sequence, Tuple

Matrix = List[List[float]]


def identity_matrix(size: int) -> Matrix:
    return [[1.0 if row == col else 0.0 for col in range(size)] for row in range(size)]


def transpose(matrix: Sequence[Sequence[float]]) -> Matrix:
    return [list(row) for row in zip(*matrix)]


def multiply_matrices(left: Sequence[Sequence[float]], right: Sequence[Sequence[float]]) -> Matrix:
    right_t = transpose(right)
    return [
        [sum(left[row][k] * right_t[col][k] for k in range(len(right_t[col]))) for col in range(len(right_t))]
        for row in range(len(left))
    ]


def off_diagonal_norm(matrix: Sequence[Sequence[float]]) -> float:
    total = 0.0
    for row in range(len(matrix)):
        for col in range(len(matrix[row])):
            if row != col:
                total += matrix[row][col] * matrix[row][col]
    return math.sqrt(total)


def qr_decomposition(matrix: Sequence[Sequence[float]]) -> Tuple[Matrix, Matrix]:
    size = len(matrix)
    q_columns: List[List[float]] = []
    r = [[0.0 for _ in range(size)] for _ in range(size)]

    for col in range(size):
        vector = [matrix[row][col] for row in range(size)]
        for prev in range(col):
            projection = sum(q_columns[prev][row] * vector[row] for row in range(size))
            r[prev][col] = projection
            vector = [vector[row] - projection * q_columns[prev][row] for row in range(size)]

        norm = math.sqrt(sum(component * component for component in vector))
        if norm <= 1e-12:
            q_column = [0.0 for _ in range(size)]
        else:
            q_column = [component / norm for component in vector]
        q_columns.append(q_column)
        r[col][col] = norm

    q = [[q_columns[col][row] for col in range(size)] for row in range(size)]
    return q, r


def schur_decomposition(
    matrix: Sequence[Sequence[float]],
    iterations: int = 100,
    tolerance: float = 1e-10,
) -> Tuple[Matrix, Matrix]:
    size = len(matrix)
    q_total = identity_matrix(size)
    t = [list(row) for row in matrix]

    for _ in range(iterations):
        q, r = qr_decomposition(t)
        t = multiply_matrices(r, q)
        q_total = multiply_matrices(q_total, q)
        if off_diagonal_norm(t) < tolerance:
            break

    return q_total, t


def schur_health_index(covariance_matrix: Sequence[Sequence[float]]) -> Tuple[float, Matrix]:
    _, triangular = schur_decomposition(covariance_matrix)
    diagonal = [triangular[index][index] for index in range(len(triangular))]
    dominant_mode = max(abs(value) for value in diagonal) if diagonal else 0.0
    return dominant_mode, triangular
