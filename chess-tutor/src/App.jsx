import { useEffect, useRef } from "react";
import { Chessboard2 } from "/node_modules/@chrisoakman/chessboard2/dist/chessboard2.min.mjs";
import { Chess } from "chess.js";

import "./App.css";
import "/node_modules/@chrisoakman/chessboard2/dist/chessboard2.min.css";

function App() {
  const chessboardRef = useRef(null);
  const chessRef = useRef(new Chess());

  useEffect(() => {
    const boardConfig = {
      draggable: true,
      position: "start",
      onDrop: (source, target) => {
        // Attempt to make a move
        const move = chessRef.current.move({
          from: source,
          to: target,
          promotion: "q", // NOTE: Always promote to a queen for example simplicity
        });

        // Illegal move
        if (move === null) return "snapback";

        // Update the board position after the piece snap
        // For castling, en passant, pawn promotion
        chessboardRef.current.position(chessRef.current.fen());

        // Check if the game is over

        /*if (chessRef.current.game_over()) {
          console.log('Game over');
        }*/
        
      },
    };

    chessboardRef.current = Chessboard2("myBoard", boardConfig);

    // Random move logic (for demonstration purposes)

    return () => {
      // Clean up the chessboard if the component unmounts
      if (chessboardRef.current) {
        chessboardRef.current.destroy();
      }
    };
  }, []);

  return (
    <>
      <div className="flex flex-col p-2">
        <div className="shadow border bg-white rounded w-full min-w-[25rem]">
          <h1 className="text-2xl font-bold p-4">Chess Tutor</h1>
        </div>
      </div>
      <div className="flex flex-col p-2">
        <div
          //ref={chessboardRef}
          id="myBoard"
          className="shadow border bg-white rounded p-4 w-full min-w-[40rem] min-h-[35rem]"
        ></div>
      </div>
    </>
  );
}

export default App;
