from app.scheduling.flow_shop.simulator import FlowShopSimulator
jobs = ['E','C','D','B','A']
proc = {'E':[4,12],'C':[6,10],'D':[12,14],'B':[16,8],'A':[10,2]}
result = FlowShopSimulator.simulate(jobs, proc)
print('Result:', result)
