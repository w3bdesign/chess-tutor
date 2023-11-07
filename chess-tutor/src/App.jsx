import { useEffect, useRef, useState } from "react";
import { Chessboard2 } from "/node_modules/@chrisoakman/chessboard2/dist/chessboard2.min.mjs";
import { Chess } from "chess.js";

import "./App.css";
import "/node_modules/@chrisoakman/chessboard2/dist/chessboard2.min.css";

function App() {
  const chessboardRef = useRef(null);
  const chessRef = useRef(new Chess());
  const [moveHistory, setMoveHistory] = useState([]);

  useEffect(() => {
    const boardConfig = {
      draggable: true,
      position: "start",
      onDrop: ({ source, target }) => {
        const move = chessRef.current.move({
          from: source,
          to: target,
          promotion: 'q' // NOTE: Always promote to a queen for example simplicity
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

  // Function to get the appropriate emoji for a piece
  const getPieceEmoji = (piece) => {
    const pieceEmojis = {
      p: '♟️', // pawn
      n: '♞', // knight
      b: '♝', // bishop
      r: '♜', // rook
      q: '♛', // queen
      k: '♚', // king
    };
    return pieceEmojis[piece.toLowerCase()] || '';
  };

  // Function to format move into algebraic notation
  const formatMove = (move) => {
    return move.san; // 'san' is the property for Standard Algebraic Notation
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
              {moveHistory.map((move, index) => {
                const moveNumber = Math.floor(index / 2) + 1;
                if (index % 2 === 0) {
                  // White's move
                  return (
                    <tr key={index}>
                      <td className="px-4 py-2">{moveNumber}.</td>
                      <td className="px-4 py-2">
                        {formatMove(move)}
                      </td>
                      {index + 1 === moveHistory.length && (
                        <td className="px-4 py-2"></td> // Empty cell if black hasn't moved yet
                      )}
                    </tr>
                  );
                } else {
                  // Black's move
                  return (
                    <tr key={index}>
                      <td className="px-4 py-2"></td> {/* Empty cell for move number */}
                      <td className="px-4 py-2"></td> {/* Empty cell for white's move */}
                      <td className="px-4 py-2">
                        {formatMove(move)}
                      </td>
                    </tr>
                  );
                }
              })}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

export default App;
