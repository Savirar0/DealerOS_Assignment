import DisagreementsTable from './components/DisagreementsTable';
import RecordsTable from './components/RecordsTable';
import './index.css';

function App() {
  return (
    <div>
      <DisagreementsTable />
      <div style={{ marginTop: '24px' }}>
        <RecordsTable />
      </div>
    </div>
  );
}

export default App;

