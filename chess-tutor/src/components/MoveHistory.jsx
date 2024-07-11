import React from "react";

/**
 * Returns the corresponding emoji for a given chess piece.
 *
 * @param {string} piece - The chess piece to get the emoji for.
 * @return {string} The emoji corresponding to the given chess piece.
 */
const getPieceEmoji = (piece) => {
  const pieceEmojis = {
    p: "♙", // pawn
    n: "♞", // knight
    b: "♝", // bishop
    r: "♜", // rook
    q: "♛", // queen
    k: "♚", // king
  };
  return pieceEmojis[piece.toLowerCase()] || "";
};

/**
 * Formats a move by adding an emoji for the piece that was moved.
 *
 * @param {object} move - The move to be formatted.
 * @param {string} move.piece - The piece that was moved.
 * @param {string} move.san - The Standard Algebraic Notation of the move.
 * @return {string} The formatted move in Standard Algebraic Notation followed by the emoji.
 */
const formatMove = (move) => {
  // Get the emoji for the piece that was moved
  const emoji = getPieceEmoji(move.piece);
  // Return the move in Standard Algebraic Notation followed by the emoji
  return `${emoji}${move.san}`;
};

/**
 * Renders a component that displays the move history of a chess game.
 *
 * @param {Object} movePairs - An array of move pairs.
 * @param {Function} formatMove - A function that formats a move.
 * @return {JSX.Element} A React component that displays the move history.
 */
const MoveHistory = ({ movePairs }) => {
  return (
    <div className="move-history shadow border bg-white rounded ml-4 pt-2 mt-2 min-h-[50rem] pr-[5rem] text-center">
      <table className="min-w-full">
        <thead>
          <tr>
            <th className="px-4 py-2">Move</th>
            <th className="px-4 py-2">White</th>
            <th className="px-4 py-2">Black</th>
          </tr>
        </thead>
        <tbody>
          {movePairs.map((pair, index) => (
            <tr key={index}>
              <td className="px-4 py-2">{index + 1}.</td>
              <td className="px-4 py-2">
                {pair.white ? formatMove(pair.white) : ""}
              </td>
              <td className="px-4 py-2">
                {pair.black ? formatMove(pair.black) : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default MoveHistory;
