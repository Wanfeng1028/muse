import {expect,it} from 'vitest';
import {buildPlaySceneImageUrl} from '../components/chat/ToolExecutionSteps';

it('binds a current scene image to its prose variant and rejects the stale turn-only image',()=>{
 const details={kind:'play_turn_revised' as const,turn:10,sceneText:'Current variant',suggestedActions:[]};
 const run={sceneImageUrls:{'scene-turn-10':'/old.png'},currentSceneImage:{turn:10,sceneText:'Current variant\n',url:'/current.png'}};
 expect(buildPlaySceneImageUrl(details,run)).toBe('/api/v1/current.png');
 expect(buildPlaySceneImageUrl({...details,sceneText:'Previous variant'},run)).toBeNull();
 expect(buildPlaySceneImageUrl(details,{...run,currentSceneImage:{...run.currentSceneImage,url:null}})).toBeNull();
 expect(buildPlaySceneImageUrl({...details,turn:undefined},null)).toBeNull();
});
