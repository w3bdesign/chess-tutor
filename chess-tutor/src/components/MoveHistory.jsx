import React from "react";

/**
 * Returns the corresponding Unicode character for a given chess piece.
 *
 * @param {string} piece - The chess piece to get the Unicode character for.
 * @param {string} color - The color of the piece ('white' or 'black').
 * @return {string} The Unicode character corresponding to the given chess piece.
 */
const getPieceUnicode = (piece, color) => {
  const pieceUnicodes = {
    white: {
      p: "♙", // pawn
      n: "♘", // knight
      b: "♗", // bishop
      r: "♖", // rook
      q: "♕", // queen
      k: "♔", // king
    },
    black: {
      p: "♟", // pawn
      n: "♞", // knight
      b: "♝", // bishop
      r: "♜", // rook
      q: "♛", // queen
      k: "♚", // king
    },
  };
  return pieceUnicodes[color][piece.toLowerCase()] || "";
};

/**
 * Formats a move by adding a Unicode character for the piece that was moved.
 *
 * @param {object} move - The move to be formatted.
 * @param {string} move.piece - The piece that was moved.
 * @param {string} move.san - The Standard Algebraic Notation of the move.
 * @param {string} color - The color of the piece ('white' or 'black').
 * @return {string} The formatted move in Standard Algebraic Notation followed by the Unicode character.
 */
const formatMove = (move, color) => {
  const unicode = getPieceUnicode(move.piece, color);
  return `${unicode}${move.san}`;
};

/**
 * Renders a component that displays the move history of a chess game.
 *
 * @param {Object} movePairs - An array of move pairs.
 * @return {JSX.Element} A React component that displays the move history.
 */
const MoveHistory = ({ movePairs }) => {
  return (
    <div className="move-history shadow border bg-white rounded ml-4 pt-2 mt-2 min-h-[50rem] min-w-[19rem]">
      <table className="min-w-full">
        <thead>
          <tr>
            <th className="px-4 py-2 text-center min-w-[60px]">Move</th>
            <th className="px-4 py-2 text-center min-w-[100px]">White</th>
            <th className="px-4 py-2 text-center min-w-[100px]">Black</th>
          </tr>
        </thead>
        <tbody>
          {movePairs.map((pair, index) => (
            <tr key={index}>
              <td className="px-4 py-2 text-center min-w-[60px]">
                {index + 1}.
              </td>
              <td className="px-4 py-2 text-center min-w-[100px]">
                {pair.white ? formatMove(pair.white, "white") : ""}
              </td>
              <td className="px-4 py-2 text-center min-w-[100px]">
                {pair.black ? formatMove(pair.black, "black") : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default MoveHistory;
