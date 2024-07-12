import ChessBoard from "./components/ChessBoard";
import MoveHistory from "./components/MoveHistory";

import "./App.css";
import "@chrisoakman/chessboard2/dist/chessboard2.min.css";

function App() {
  return (
    <div className="container mx-auto p-4">
      <div className="shadow border bg-white rounded w-full mb-4">
        <h1 className="text-2xl font-bold p-4">Chess Tutor</h1>
      </div>
      <div className="flex flex-col lg:flex-row gap-4">
        <div className="lg:w-2/3">
          <ChessBoard />
        </div>
        <div className="lg:w-1/3">
          <MoveHistory />
        </div>
      </div>
    </div>
  );
}

export default App;
