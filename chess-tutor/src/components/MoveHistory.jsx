import React from 'react';

/**
 * Renders a component that displays the move history of a chess game.
 *
 * @param {Object} movePairs - An array of move pairs.
 * @param {Function} formatMove - A function that formats a move.
 * @return {JSX.Element} A React component that displays the move history.
 */
const MoveHistory = ({ movePairs, formatMove }) => {
  return (
    <div className="move-history shadow border bg-white rounded p-4 mt-4">
      <h2 className="text-xl font-bold">Move History</h2>
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
