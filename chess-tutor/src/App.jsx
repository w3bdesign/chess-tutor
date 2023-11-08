import { useEffect, useRef, useState } from "react";
import { Chessboard2 } from "/node_modules/@chrisoakman/chessboard2/dist/chessboard2.min.mjs";
import { Chess } from "chess.js";

import "./App.css";
import "/node_modules/@chrisoakman/chessboard2/dist/chessboard2.min.css";

function App() {
  const chessboardRef = useRef(null);
  const chessRef = useRef(new Chess());

  const [moveHistory, setMoveHistory] = useState([]);
  const [movePairs, setMovePairs] = useState([]);

  useEffect(() => {
    // Update movePairs whenever moveHistory changes
    const pairs = [];
    for (let i = 0; i < moveHistory.length; i += 2) {
      pairs.push({
        white: moveHistory[i],
        black: moveHistory[i + 1] || null, // Black move might not exist yet
      });
    }
    setMovePairs(pairs);
  }, [moveHistory]);

  useEffect(() => {
    const boardConfig = {
      draggable: true,
      position: "start",
      onDrop: ({ source, target }) => {
        const move = chessRef.current.move({
          from: source,
          to: target,
          promotion: "q", // NOTE: Always promote to a queen for example simplicity
        });

        if (move === null) return "snapback";

        chessboardRef.current.position(chessRef.current.fen());
        setMoveHistory(chessRef.current.history({ verbose: true }));
      },
    };

    chessboardRef.current = Chessboard2("myBoard", boardConfig);

    return () => {
      if (chessboardRef.current) {
        chessboardRef.current.destroy();
      }
    };
  }, []);

  /**
   * Returns the corresponding emoji for a given chess piece.
   *
   * @param {string} piece - The chess piece to get the emoji for.
   * @return {string} The emoji corresponding to the given chess piece.
   */
  const getPieceEmoji = (piece) => {
    const pieceEmojis = {
      p: "♟️", // pawn
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

  return (
    <>
      <div className="flex flex-col p-2">
        <div className="shadow border bg-white rounded w-full min-w-[25rem]">
          <h1 className="text-2xl font-bold p-4">Chess Tutor</h1>
        </div>
      </div>
      <div className="flex flex-col p-2">
        <div
          id="myBoard"
          className="shadow border bg-white rounded p-4 w-full min-w-[40rem] min-h-[35rem]"
        ></div>

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
        
      </div>
    </>
  );
}

export default App;
